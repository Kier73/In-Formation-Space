"""RCG-002: durable, source-pinned continuity for real-connectome Grounds.

One durable record binds a complete source snapshot; later records bind verified
query capsules or proposed training episodes. This is an integrity ledger, not
an external signature, distributed consensus service or biological simulator.
"""
from __future__ import annotations

from contextlib import contextmanager
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any, Iterator

from connectome_ground import ConnectomeGround, ConnectomeRefused, Query, canonical, sha
from query_attribution import attribute

SCHEMA = 'ifs.real-connectome-continuity.v1'
HEX64 = re.compile(r'[0-9a-f]{64}\Z')
GENESIS = sha({'schema': SCHEMA, 'kind': 'genesis'})


class ContinuityRefused(ValueError):
    """The retained structure, source pin, query or lineage is insufficient."""


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _validate_digest(value: Any) -> str:
    if type(value) is not str or HEX64.fullmatch(value) is None:
        raise ContinuityRefused('expected a complete SHA-256 hexadecimal pin')
    return value


def _write_immutable(path: Path, value: bytes) -> None:
    """Write-once content, durable across a normal process restart."""
    if path.exists():
        if path.read_bytes() != value:
            raise ContinuityRefused('immutable object conflicts with existing content')
        return
    fd, tmp = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        # Guard against preexisting destination, never overwrite an accepted object.
        try:
            os.link(tmp, path)
        except FileExistsError:
            if path.read_bytes() != value:
                raise ContinuityRefused('immutable object collision')
        _fsync_directory(path.parent)
    finally:
        Path(tmp).unlink(missing_ok=True)


def _fsync_directory(path: Path) -> None:
    if os.name != 'nt':
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _load_json(raw: bytes) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except (UnicodeError, ValueError, TypeError) as exc:
        raise ContinuityRefused('malformed canonical JSON record') from exc
    if type(value) is not dict or canonical(value) != raw:
        raise ContinuityRefused('record must use canonical JSON and be an object')
    return value


def source_manifest(ground: ConnectomeGround) -> dict[str, Any]:
    """Construct a frozen, testable identity for an admitted original source."""
    kinds = {kind: sum(edge.kind == kind for edge in ground.edges)
             for kind in ('chemical', 'electrical')}
    body = {'schema': SCHEMA + '.source.v1', 'source_id': ground.source_id,
            'git_blob_sha1': ground.source_blob, 'ground_fingerprint': ground.fingerprint,
            'node_labels': len(ground.nodes), 'recorded_edges': len(ground.edges),
            'synapse_types': kinds,
            'observation_model': 'unsigned-outgoing-synapse-count-normalized-exact-horizon',
            'status': 'source-observed-dynamics-unverified'}
    return {**body, 'digest': sha(body)}


def queried_capsule(ground: ConnectomeGround, query: Query) -> dict[str, Any]:
    """Run existing RCG-001 algorithm and separate independent reference oracle."""
    plan = ground.plan(query)
    receipt = ground.run(plan)
    actual = ground.verify(plan, receipt, whole_graph=True)
    # Existing attribution uses the same verified Ground, not a second algorithm.
    attribution = attribute(ground, plan, receipt)
    return {'schema': SCHEMA + '.query-capsule.v1', 'source': ground.source_blob,
            'ground': ground.fingerprint, 'query': query.encode(),
            'plan': plan, 'observation': receipt, 'attribution': attribution,
            'independent_full_reference': f'{actual.numerator}/{actual.denominator}',
            'interpretation': 'structural transfer under declared positive normalized weights; NOT biological spike activity'}


class Chronicle:
    """Crash-detectable append-only ledger; no authentication without external pin."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self.objects = self.directory / 'objects'
        self.ledger = self.directory / 'lineage.jsonl'
        self.lock = self.directory / '.writer.lock'

    def _prepare(self) -> None:
        self.objects.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _writer(self) -> Iterator[None]:
        self._prepare()
        try:
            fd = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise ContinuityRefused('another writer owns the continuity root; do not race') from exc
        try:
            with os.fdopen(fd, 'w') as stream:
                stream.write(str(os.getpid()))
                stream.flush()
                os.fsync(stream.fileno())
            yield
        finally:
            self.lock.unlink(missing_ok=True)

    def verify(self, *, expected_head: str | None = None) -> list[dict[str, Any]]:
        """Validate every object and complete chain, optionally against an external pin."""
        if expected_head is not None:
            _validate_digest(expected_head)
        if not self.ledger.exists():
            if expected_head is not None and expected_head != GENESIS:
                raise ContinuityRefused('externally pinned history is missing')
            return []
        history = []
        parent = GENESIS
        data = self.ledger.read_bytes()
        if data and not data.endswith(b'\n'):
            raise ContinuityRefused('truncated ledger tail; refuse uncertain history')
        for sequence, raw in enumerate(data.splitlines()):
            record = _load_json(raw)
            if set(record) != {'schema', 'index', 'parent', 'kind', 'object', 'head'} or \
                    record['schema'] != SCHEMA + '.event.v1' or \
                    type(record['index']) is not int or record['index'] != sequence or \
                    record['parent'] != parent or record['kind'] not in ('source', 'query', 'training-plan'):
                raise ContinuityRefused('lineage ordering, schema or predecessor mismatch')
            object_digest = _validate_digest(record['object'])
            object_path = self.objects / (object_digest + '.json')
            if not object_path.is_file():
                raise ContinuityRefused('referenced Ground object is missing')
            object_bytes = object_path.read_bytes()
            if _hash(object_bytes) != object_digest:
                raise ContinuityRefused('Ground object bytes differ from content address')
            _load_json(object_bytes)
            derived = sha({k: v for k, v in record.items() if k != 'head'})
            if record['head'] != derived:
                raise ContinuityRefused('lineage hash chain fails independent reconstruction')
            if sequence == 0 and record['kind'] != 'source':
                raise ContinuityRefused('Ground history must begin with one source snapshot')
            if sequence > 0 and record['kind'] == 'source':
                raise ContinuityRefused('source cannot silently change within existing history')
            if record['kind'] == 'query':
                capsule = _load_json(object_bytes)
                if capsule.get('schema') != SCHEMA + '.query-capsule.v1':
                    raise ContinuityRefused('query event refers to incorrect capsule schema')
            parent = derived
            history.append(record)
        if expected_head is not None and parent != expected_head:
            raise ContinuityRefused('lineage disagrees with independently held trusted high-water pin')
        return history

    def _append(self, kind: str, value: dict[str, Any], *, expected_head: str | None = None) -> dict[str, Any]:
        if kind not in ('source', 'query', 'training-plan') or type(value) is not dict:
            raise ContinuityRefused('unsupported continuity event')
        value_bytes = canonical(value)
        with self._writer():
            history = self.verify(expected_head=expected_head)
            if (not history and kind != 'source') or (history and kind == 'source'):
                raise ContinuityRefused('source must be unique and precede training/query records')
            object_digest = _hash(value_bytes)
            _write_immutable(self.objects / (object_digest + '.json'), value_bytes)
            body = {'schema': SCHEMA + '.event.v1', 'index': len(history),
                    'parent': history[-1]['head'] if history else GENESIS,
                    'kind': kind, 'object': object_digest}
            record = {**body, 'head': sha(body)}
            # Appending is atomic to logical reader only after fsync. A crash
            # during write may leave a truncated tail that verifier refuses.
            with self.ledger.open('ab') as stream:
                stream.write(canonical(record) + b'\n')
                stream.flush()
                os.fsync(stream.fileno())
            _fsync_directory(self.directory)
            return record

    def source(self, ground: ConnectomeGround, *, expected_head: str | None = None) -> dict[str, Any]:
        value = source_manifest(ground)
        if self.verify(expected_head=expected_head):
            prior = self.read_event(0)
            if prior != value:
                raise ContinuityRefused('persisted Ground source identity differs from current source')
            return self.verify()[-1]
        return self._append('source', value, expected_head=expected_head)

    def read_event(self, index: int) -> dict[str, Any]:
        history = self.verify()
        if type(index) is not int or not 0 <= index < len(history):
            raise ContinuityRefused('no retained record exists at selected position')
        return _load_json((self.objects / (history[index]['object'] + '.json')).read_bytes())

    def query(self, ground: ConnectomeGround, request: Query, *, expected_head: str) -> dict[str, Any]:
        history = self.verify(expected_head=expected_head)
        if not history or self.read_event(0) != source_manifest(ground):
            raise ContinuityRefused('query Ground differs from retained original source')
        return self._append('query', queried_capsule(ground, request), expected_head=expected_head)

    def training_plan(self, ground: ConnectomeGround, opportunity: dict[str, Any], *,
                      expected_head: str) -> dict[str, Any]:
        history = self.verify(expected_head=expected_head)
        if not history or self.read_event(0) != source_manifest(ground):
            raise ContinuityRefused('training intention not bound to retained source')
        if type(opportunity) is not dict or type(opportunity.get('id')) is not str or \
                opportunity.get('status') != 'proposed':
            raise ContinuityRefused('training proposal must remain explicitly proposed')
        record = {'schema': SCHEMA + '.training-intention.v1',
                  'ground': ground.fingerprint, 'source_blob': ground.source_blob,
                  'opportunity': opportunity,
                  'not_observed_training_or_a_model_checkpoint': True}
        return self._append('training-plan', record, expected_head=expected_head)

    def audit(self, ground: ConnectomeGround, *, expected_head: str) -> dict[str, Any]:
        """Independently re-execute every persisted query under the pinned source."""
        history = self.verify(expected_head=expected_head)
        if not history or self.read_event(0) != source_manifest(ground):
            raise ContinuityRefused('persistent source differs from admissible original Ground')
        counts = {'source': 1, 'query': 0, 'training-plan': 0}
        for index, entry in enumerate(history[1:], start=1):
            capsule = self.read_event(index)
            if entry['kind'] == 'query':
                try:
                    query = Query(**capsule['query'])
                    expected = queried_capsule(ground, query)
                except (KeyError, TypeError, ConnectomeRefused) as exc:
                    raise ContinuityRefused('persisted query cannot be reconstructed from source') from exc
                if canonical(capsule) != canonical(expected):
                    raise ContinuityRefused('persisted observation differs from independently recomputed Ground')
            elif entry['kind'] == 'training-plan':
                if capsule.get('schema') != SCHEMA + '.training-intention.v1' or \
                        capsule.get('ground') != ground.fingerprint or \
                        capsule.get('source_blob') != ground.source_blob or \
                        capsule.get('opportunity', {}).get('status') != 'proposed' or \
                        capsule.get('not_observed_training_or_a_model_checkpoint') is not True:
                    raise ContinuityRefused('training intention falsely claims authority or observed learning')
            counts[entry['kind']] += 1
        return {'schema': SCHEMA + '.audit.v1', 'ground': ground.fingerprint,
                'head': history[-1]['head'], 'counts': counts,
                'status': 'verified-mathematical-structure-not-biological-validation'}


def bootstrap_original(root: Path, *, path: Path | None = None) -> ConnectomeGround:
    source = path or (Path(__file__).parents[1] / 'data' / 'herm_full_edgelist.csv')
    return ConnectomeGround.from_csv(source.read_bytes())


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description='RCG-002 append-only, source-pinned connectome continuity')
    p.add_argument('--store', type=Path, required=True)
    p.add_argument('--source', type=Path)
    p.add_argument('--expected-head', help='External independently retained previous history head')
    p.add_argument('--from-node', default='ASHL')
    p.add_argument('--to-node', default='AVAL')
    p.add_argument('--steps', type=int, default=3)
    p.add_argument('--kind', default='chemical', choices=['chemical', 'electrical'])
    p.add_argument('action', choices=['init', 'query', 'verify', 'audit'])
    args = p.parse_args()
    chronicle = Chronicle(args.store)
    if args.action == 'verify':
        result = chronicle.verify(expected_head=args.expected_head)
        print(json.dumps({'records': len(result), 'head': result[-1]['head'] if result else GENESIS}))
        return
    ground = bootstrap_original(args.store, path=args.source)
    if args.action == 'audit':
        if args.expected_head is None:
            raise ContinuityRefused('auditing requires externally pinned high-water head')
        print(json.dumps(chronicle.audit(ground, expected_head=args.expected_head), sort_keys=True))
        return
    if args.action == 'init':
        record = chronicle.source(ground, expected_head=args.expected_head)
    else:
        if args.expected_head is None:
            raise ContinuityRefused('queries require an external expected-head pin')
        record = chronicle.query(ground, Query(args.from_node, args.to_node, args.steps, args.kind),
                                 expected_head=args.expected_head)
    print(json.dumps({'index': record['index'], 'head': record['head'],
                      'ground': ground.fingerprint, 'kind': record['kind']}))


if __name__ == '__main__':
    main()
