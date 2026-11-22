"""SFI-004: proof-rechecked, source-refinement-aware structural memory.

The stored artifact is not an authority or a SAT answer. It is a previously
qualified Boolean interpreter which may remain a *candidate architecture*
for an exact strengthening of its source CNF. Every reuse is independently
reverified from the current source, and all observations are source-replayed.

Single-writer local-file research prototype. It does not authenticate records,
provide quorum durability or transfer E-CPU effect permissions across hosts.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from time import perf_counter_ns
import json
import math
import os
import tempfile

from morphic_sat import compile_ground, digest, execute, normalize
from morphic_verifier import verify, check_partition
from recursive_sat_compiler import refine, audit_refinement

SCHEMA = 'sfi.structural-construction-memory.v1'
RECORD = 'sfi.construction-record.v1'
OBS = 'sfi.construction-observation.v1'
MAX_RECORDS = 128
MAX_OBSERVATIONS = 256
MAX_FILE_BYTES = 16 << 20
_ZERO = '0' * 64


def _identity(obj):
    return digest({k: v for k, v in obj.items() if k != 'digest'})


def _source(clauses, n):
    return [list(c) for c in normalize(clauses, n)]


def _require_time(value):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
        raise ValueError('invalid untrusted performance observation')


def _rebase(prior, target):
    """Recompose exactly the old gate blocks and the new source residual.

    The gate program is never 'patched' according to reported performance. An
    addition that removes a past solution is evaluated as a fresh residual
    constraint; a removed defining clause forbids reuse.
    """
    if not isinstance(prior, dict):
        raise ValueError('missing ancestor machine')
    n = prior['n']
    original = {tuple(c) for c in prior['source_clauses']}
    newer = {tuple(c) for c in target}
    if not original.issubset(newer):
        raise ValueError('source weakened or changed: no proven monotone reuse')
    used = {tuple(clause) for gate in prior['instructions']
            for clause in gate['clauses']}
    if not used.issubset(newer):
        raise ValueError('old function-defining clause disappeared')
    result = deepcopy(prior)
    result['source_clauses'] = deepcopy(target)
    result['residual'] = [list(c) for c in target if tuple(c) not in used]
    result['digest'] = _identity(result)
    verify(result, max_free=256)
    if result['n'] != n or result['instructions'] != prior['instructions']:
        raise ValueError('reused architecture changed')
    return result


def _check_record(record, known, previous):
    if type(record) is not dict or set(record) != {
        'schema','ordinal','previous','source_n','source_clauses','source_sha256',
        'ground','method','parent_record','refinement_report',
        'baseline_registers','construction_ms','digest'}:
        raise ValueError('malformed stored construction')
    if record['schema'] != RECORD or record['previous'] != previous or \
       type(record['ordinal']) is not int or record['ordinal'] != len(known) + 1 or \
       record['digest'] != _identity(record):
        raise ValueError('broken structural-memory chain')
    n = record['source_n']
    source = _source(record['source_clauses'], n)
    if source != record['source_clauses'] or record['source_sha256'] != digest({'n':n,'clauses':source}):
        raise ValueError('source identity changed')
    _require_time(record['construction_ms'])
    ground = record['ground']
    if ground['n'] != n or ground['source_clauses'] != source:
        raise ValueError('stored Ground is unrelated to source')
    if not verify(ground, max_free=256)['proven']:
        raise ValueError('stored Ground does not prove source equivalence')
    mode = record['method']
    if mode == 'self-refinement':
        if record['parent_record'] is not None:
            raise ValueError('initial self-refinement cannot inherit an unqualified source')
        audit_refinement(source, n, ground, record['refinement_report'])
    elif mode == 'fresh-baseline':
        if record['parent_record'] is not None or record['refinement_report'] is not None:
            raise ValueError('fresh compiler record claims an ancestor')
        rebuilt, _ = compile_ground(source, n)
        if rebuilt != ground:
            raise ValueError('stored fallback differs from deterministic baseline')
    elif mode == 'monotone-reuse':
        if record['refinement_report'] is not None:
            raise ValueError('reuse cannot claim a new meta-SAT optimization proof')
        ancestor = known.get(record['parent_record'])
        if ancestor is None or ancestor['source_n'] != n:
            raise ValueError('reuse references missing or incompatible ancestor')
        if _rebase(ancestor['ground'], source) != ground:
            raise ValueError('reuse is not an exact monotone source extension')
    else:
        raise ValueError('unknown stored construction kind')
    # Fresh deterministic baseline is the qualification comparison, including
    # when the stored gate selection was optimized by SFI-003.
    baseline, _ = compile_ground(source, n)
    if record['baseline_registers'] != len(baseline['registers']):
        raise ValueError('stale baseline coordinate claim')
    if len(ground['registers']) > len(baseline['registers']):
        raise ValueError('stored construction worsens verified coordinate dimension')
    if mode == 'monotone-reuse' and len(ground['registers']) >= len(baseline['registers']):
        raise ValueError('reused ground has no strict structural advantage')
    return True


def _check_observation(observation, known):
    if type(observation) is not dict or set(observation) != {
        'schema','record_id','intent','coordinate_budget','partition_size',
        'result','elapsed_ms','digest'} or observation.get('schema') != OBS or \
       observation.get('digest') != _identity(observation):
        raise ValueError('invalid observed computation record')
    record = known.get(observation['record_id'])
    if record is None:
        raise ValueError('observation references missing construction')
    _require_time(observation['elapsed_ms'])
    intention = observation['intent']
    limit = observation['coordinate_budget']
    size = observation['partition_size']
    if intention not in ('SAT','#SAT') or type(limit) is not int or \
       not 0 <= limit <= (1 << 20) or type(size) is not int or not 1 <= size <= (1 << 20):
        raise ValueError('invalid observer intention or resource budget')
    ground = record['ground']
    result = observation['result']
    if type(result) is not dict:
        raise ValueError('missing result')
    # Replay from the independently source-qualified machine. Stored wall
    # times play NO role in accepting the mathematical decision/count.
    actual = execute(ground, intent='COUNT' if intention == '#SAT' else 'SAT',
                     max_coordinates=limit, partition_size=size)
    if actual != result:
        raise ValueError('stored computation differs from original-source replay')
    for part in result.get('partition_receipts', []):
        check_partition(ground, part, maximum=limit, partition_size=size)
    return True


def verify_memory(payload):
    """Reconstruct source semantics and receipts; digests alone are not proofs."""
    if type(payload) is not dict or set(payload) != {'schema','records','observations','digest'} or \
       payload['schema'] != SCHEMA or payload['digest'] != _identity(payload) or \
       type(payload['records']) is not list or type(payload['observations']) is not list or \
       len(payload['records']) > MAX_RECORDS or len(payload['observations']) > MAX_OBSERVATIONS:
        raise ValueError('invalid memory image')
    known={}
    previous=_ZERO
    for record in payload['records']:
        _check_record(record, known, previous)
        known[record['digest']] = record
        previous = record['digest']
    for observation in payload['observations']:
        _check_observation(observation, known)
    return {'qualified_constructions':len(known),
            'source_checked_observations':len(payload['observations']),
            'memory_digest':payload['digest']}


def _empty():
    x = {'schema':SCHEMA,'records':[],'observations':[]}
    x['digest'] = _identity(x)
    return x


class ConstructionMemory:
    """A local single-writer, fail-closed snapshot of qualified constructions."""

    def __init__(self, filename):
        self.path=Path(filename)
        self._verified_cache=None  # (sha256(exact disk bytes), independently qualified image)
        if not self.path.name:
            raise ValueError('memory needs a concrete file path')

    def read(self):
        if not self.path.exists():
            if self._verified_cache is not None:
                raise ValueError('previously verified memory image disappeared')
            return _empty()
        raw = self.path.read_bytes()
        if len(raw)>MAX_FILE_BYTES:
            raise ValueError('memory image exceeds bounded byte contract')
        fingerprint=sha256(raw).digest()
        if self._verified_cache is not None:
            if self._verified_cache[0] != fingerprint:
                raise ValueError('memory was rewritten outside this qualified writer; reopen a fresh reader')
            return deepcopy(self._verified_cache[1])
        try:
            image=json.loads(raw)
        except (UnicodeDecodeError,json.JSONDecodeError) as exc:
            raise ValueError('memory image cannot be parsed') from exc
        verify_memory(image)
        self._verified_cache=(fingerprint,deepcopy(image))
        return deepcopy(image)

    def _write(self, payload):
        """Validate only the new event against an unchanged qualified prefix.

        This is a single-writer optimization, NOT a cross-process CAS or a
        signature. A new process audits the entire history on first read.
        Never trust the producer's digest without verifying the new event.
        """
        if self.path.exists():
            raw_before=self.path.read_bytes()
            actual_sha=sha256(raw_before).digest()
            if self._verified_cache is None or self._verified_cache[0]!=actual_sha:
                raise ValueError('memory changed since last qualified read')
            previous=self._verified_cache[1]
        else:
            if self._verified_cache is not None:
                raise ValueError('qualified memory vanished before publication')
            previous=_empty()
        payload['digest']=_identity(payload)
        if (type(payload) is not dict or payload.get('schema')!=SCHEMA or
            type(payload.get('records')) is not list or
            type(payload.get('observations')) is not list or
            len(payload['records'])>MAX_RECORDS or
            len(payload['observations'])>MAX_OBSERVATIONS):
            raise ValueError('invalid bounded next memory image')
        if (payload['records'][:-1]==previous['records'] and
            len(payload['records'])==len(previous['records'])+1 and
            payload['observations']==previous['observations']):
            latest=payload['records'][-1]
            known={x['digest']:x for x in previous['records']}
            prior=previous['records'][-1]['digest'] if previous['records'] else _ZERO
            _check_record(latest,known,prior)
        elif (payload['records']==previous['records'] and
              payload['observations'][:-1]==previous['observations'] and
              len(payload['observations'])==len(previous['observations'])+1):
            known={x['digest']:x for x in previous['records']}
            _check_observation(payload['observations'][-1],known)
        else:
            raise ValueError('memory transition is not one qualified append')
        raw=json.dumps(payload,sort_keys=True,separators=(',',':'),
                       allow_nan=False).encode('utf-8')
        if len(raw)>MAX_FILE_BYTES:
            raise ValueError('memory image exceeds bounded byte contract')
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,temporary=tempfile.mkstemp(prefix='.construction-memory-',dir=self.path.parent)
        try:
            with os.fdopen(fd,'wb') as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary,self.path)
            if os.name != 'nt':
                directory_fd=os.open(self.path.parent,os.O_RDONLY)
                try:os.fsync(directory_fd)
                finally:os.close(directory_fd)
        finally:
            if os.path.exists(temporary):os.unlink(temporary)
        self._verified_cache=(sha256(raw).digest(),deepcopy(payload))
        return payload

    def _add(self,image,source,n,ground,method,parent,report,build_ms,baseline_registers):
        if len(image['records'])>=MAX_RECORDS:
            raise ValueError('memory construction capacity reached')
        record={'schema':RECORD,'ordinal':len(image['records'])+1,
                'previous':image['records'][-1]['digest'] if image['records'] else _ZERO,
                'source_n':n,'source_clauses':source,
                'source_sha256':digest({'n':n,'clauses':source}),
                'ground':deepcopy(ground),'method':method,'parent_record':parent,
                'refinement_report':deepcopy(report),
                'baseline_registers':baseline_registers,
                'construction_ms':round(build_ms,4)}
        record['digest']=_identity(record)
        image['records'].append(record)
        self._write(image)
        return deepcopy(record)

    def bootstrap(self,clauses,n,*,self_refine=True):
        """Produce an independently qualified first machine, optionally via meta-SAT."""
        image=self.read()
        if image['records']:
            raise ValueError('memory already bootstrapped')
        source=_source(clauses,n)
        start=perf_counter_ns()
        if self_refine:
            ground,report=refine(source,n)
            audit_refinement(source,n,ground,report)
            method='self-refinement'
        else:
            ground,_=compile_ground(source,n)
            report=None
            method='fresh-baseline'
        verify(ground,max_free=256)
        elapsed=(perf_counter_ns()-start)/1e6
        initial_baseline=(report['baseline_registers'] if report is not None
                          else len(ground['registers']))
        return self._add(image,source,n,ground,method,None,report,elapsed,initial_baseline)

    def extend(self,clauses,n):
        """Navigate compatible prior Ground(s), select strict coordinate gains.

        Every possible target is rechecked against its *current* source; a
        fresh baseline comparison is mandatory and costs are not hidden.
        No old SAT answer, count, or E-CPU authority is carried forward.
        """
        image=self.read()
        if not image['records']:
            raise ValueError('memory must be bootstrapped')
        source=_source(clauses,n)
        start=perf_counter_ns()
        baseline,_=compile_ground(source,n)
        best=None
        for original in image['records']:
            if original['source_n'] != n:
                continue
            if not {tuple(c) for c in original['source_clauses']}.issubset(
                    {tuple(c) for c in source}):
                continue
            proposal=_rebase(original['ground'],source)
            score=(len(proposal['registers']),
                   -len(original['source_clauses']),original['ordinal'])
            if len(proposal['registers']) < len(baseline['registers']) and \
               (best is None or score<best[0]):
                best=(score,proposal,original['digest'])
        if best is None:
            ground=baseline
            method='fresh-baseline';parent=None
        else:
            ground=best[1];method='monotone-reuse';parent=best[2]
        verify(ground,max_free=256)
        elapsed=(perf_counter_ns()-start)/1e6
        return self._add(image,source,n,ground,method,parent,None,elapsed,
                         len(baseline['registers']))

    def observe(self,record_id,*,intention='#SAT',coordinate_budget=1<<16,
                partition_size=1024):
        """Carry a source-replayable observation (not a cached authority grant)."""
        image=self.read()
        if len(image['observations'])>=MAX_OBSERVATIONS:
            raise ValueError('observation capacity reached')
        records={record['digest']:record for record in image['records']}
        if record_id not in records:
            raise ValueError('unknown memory Ground')
        if intention not in ('SAT','#SAT') or type(coordinate_budget) is not int or \
           not 0<=coordinate_budget<=1<<20 or type(partition_size) is not int or \
           not 1<=partition_size<=1<<20:
            raise ValueError('invalid finite observer budget')
        start=perf_counter_ns()
        output=execute(records[record_id]['ground'],
                       intent='COUNT' if intention=='#SAT' else 'SAT',
                       max_coordinates=coordinate_budget,partition_size=partition_size)
        elapsed=(perf_counter_ns()-start)/1e6
        entry={'schema':OBS,'record_id':record_id,'intent':intention,
               'coordinate_budget':coordinate_budget,'partition_size':partition_size,
               'result':output,'elapsed_ms':round(elapsed,4)}
        entry['digest']=_identity(entry)
        image['observations'].append(entry)
        self._write(image)
        return deepcopy(entry)
