"""RCG-003 minimal separate-process observer connected by actual local stdio.

Existing E-CPU mTLS/Transit paths remain the intended remote transport;
this fixture deliberately DOES NOT implement an alternative network stack.
It cannot execute a modeled TLS or modeled GitHub-artifact path.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from connectome_ground import ConnectomeGround, Query, canonical
from adaptive_fabric.fabric_policy import (
    SCHEMA, FabricRefused, HostPath, Workload, canonical_hash, realize_selected,
)

MAX_STDIN = 24_000


def receive(original: bytes, raw: bytes, *, expected_source_sha256: str,
            require_original: bool = True, permitted_methods: tuple[str, ...] = ('cone',)) -> dict:
    if hashlib.sha256(original).hexdigest() != expected_source_sha256:
        raise FabricRefused('receiver-owned original source SHA-256 differs')
    ground = ConnectomeGround.from_csv(original, require_original=require_original)
    if len(raw) > MAX_STDIN:
        raise FabricRefused('untrusted communication frame exceeds protocol budget')
    try:
        request = json.loads(raw)
        if type(request) is not dict or set(request) != {'schema', 'ground', 'workload', 'selection'} or \
                request['schema'] != SCHEMA + '.request.v1' or \
                request['ground'] != ground.fingerprint or \
                type(request['workload']) is not dict:
            raise FabricRefused('unadmitted request schema or Ground pin')
        proposed = request['selection']
        route = HostPath(**proposed['chosen'])
        if route.medium != 'local-ipc' or route.host != 'local-worker' or \
                not route.permitted or not route.available or route.method not in permitted_methods:
            raise FabricRefused('requested host/path is not admitted by receiver policy')
        fields = request['workload']
        if set(fields) != {'ground', 'query', 'plan_digest', 'cone_edges', 'full_edges',
                           'cone_payload_bytes', 'full_payload_bytes'}:
            raise FabricRefused('workload fields do not match typed source task')
        workload = Workload(ground=fields['ground'], request=fields['query'],
                            plan_digest=fields['plan_digest'], cone_edges=fields['cone_edges'],
                            full_edges=fields['full_edges'],
                            cone_payload_bytes=fields['cone_payload_bytes'],
                            full_payload_bytes=fields['full_payload_bytes'])
    except (TypeError, ValueError, KeyError) as exc:
        raise FabricRefused('receiver refused malformed or unauthorized observation request') from exc
    result = realize_selected(ground, workload, proposed, independent=True)
    body = {'schema': SCHEMA + '.stdio-observer-receipt.v1', 'ground': ground.fingerprint,
            'medium': 'local-ipc', 'verified': result, 'request_sha256': hashlib.sha256(raw).hexdigest(),
            'status': 'separate-interpreter-observation; no-network-mtls-authority'}
    return {**body, 'digest': canonical_hash(body)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--expected-source-sha256', required=True)
    parser.add_argument('--fixture', action='store_true', help='allow local test fixture; never changes source pin verification')
    parser.add_argument('--permit-full', action='store_true')
    args = parser.parse_args()
    received = sys.stdin.buffer.read(MAX_STDIN + 1)
    response = receive(args.source.read_bytes(), received,
                       expected_source_sha256=args.expected_source_sha256,
                       require_original=not args.fixture,
                       permitted_methods=('cone', 'full') if args.permit_full else ('cone',))
    sys.stdout.buffer.write(canonical(response) + b'\n')


if __name__ == '__main__':
    try:
        main()
    except (FabricRefused, ValueError) as exc:
        print(f'REFUSED: {exc}', file=sys.stderr)
        raise SystemExit(2)
