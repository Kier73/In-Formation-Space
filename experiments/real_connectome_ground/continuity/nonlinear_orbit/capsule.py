"""Portable RCG-005 nonlinear source Ground capsules, verified by a fresh process.

No new persistence authority: files are immutable mathematical evidence to be
anchored by the existing RCG-002 Chronicle / E-CPU object storage and quorum.
GitHub/CI artifact transport is not independent permission or authentication.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from connectome_ground import ConnectomeGround
from temporal_ground import TemporalGroundRefused, SparseTransfer, hash_object
from conjugate_ground import ConjugatedGround, prepare_shared, verify_shared, \
    navigate, verify_result

MAX_CAPSULE_BYTES=250_000


def read_json_strict(path:Path)->dict[str,Any]:
    raw=path.read_bytes()
    if len(raw)>MAX_CAPSULE_BYTES or not raw:
        raise TemporalGroundRefused('untrusted neural capsule exceeds admitted size')
    def pairs(p):
        value={}
        for k,v in p:
            if k in value:
                raise TemporalGroundRefused('duplicate JSON key refused')
            value[k]=v
        return value
    def constant(s):
        raise TemporalGroundRefused(f'unadmitted non-finite JSON constant: {s}')
    try:
        result=json.loads(raw.decode('utf-8'),object_pairs_hook=pairs,parse_constant=constant)
    except (ValueError,UnicodeDecodeError) as exc:
        raise TemporalGroundRefused('malformed portable neural certificate') from exc
    if type(result) is not dict:
        raise TemporalGroundRefused('neural capsule must be a JSON object')
    return result


def write_json(path:Path,record:dict[str,Any])->None:
    output=json.dumps(record,sort_keys=True,separators=(',',':'),allow_nan=False).encode()+b'\n'
    if len(output)>MAX_CAPSULE_BYTES:
        raise TemporalGroundRefused('portable certificate exceeds admission budget')
    path.parent.mkdir(parents=True,exist_ok=True)
    # This is a command-line export, not a transactional store. The RCG-002
    # Chronicle or existing E-CPU M1 must own durable atomic object publication.
    path.write_bytes(output)


def load_model(source_file:Path, source_sha256:str,coordinates:tuple[str,...],
               *,seed:str,fixture:bool=False,kind:str='chemical')->ConjugatedGround:
    try:
        raw=source_file.read_bytes()
    except OSError as exc:
        raise TemporalGroundRefused('receiver source file unavailable') from exc
    if hashlib.sha256(raw).hexdigest()!=source_sha256:
        raise TemporalGroundRefused('receiver-owned original bytes differ from external SHA-256')
    source=ConnectomeGround.from_csv(raw,require_original=not fixture)
    op=SparseTransfer.from_ground(source,coordinates[0],coordinates[0],kind=kind)
    return ConjugatedGround(op,coordinates,seed)


def prepare_capsule(model:ConjugatedGround)->dict[str,Any]:
    certificate=prepare_shared(model)
    verify_shared(model,certificate)
    body={'schema':'ifs.rcg005.portable-source-capsule.v1',
          'model_digest':model.fingerprint,'source_blob':model.operator.blob,
          'certificate':certificate}
    return {**body,'digest':hash_object(body)}


def verify_capsule(model:ConjugatedGround,capsule:dict[str,Any])->dict[str,Any]:
    if type(capsule) is not dict or set(capsule)!={'schema','model_digest','source_blob','certificate','digest'} or \
            capsule['schema']!='ifs.rcg005.portable-source-capsule.v1' or \
            capsule['model_digest']!=model.fingerprint or \
            capsule['source_blob']!=model.operator.blob or \
            capsule['digest']!=hash_object({k:v for k,v in capsule.items() if k!='digest'}):
        raise TemporalGroundRefused('noncanonical portable Ground capsule or changed source')
    verify_shared(model,capsule['certificate'])
    return capsule['certificate']


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','verify','replay'])
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--expected-source-sha256',required=True,
                        help='independent receiver-owned source pin')
    parser.add_argument('--coordinates',nargs='+',default=['ASHL','AVAL','AVBL','AVAR'])
    parser.add_argument('--kind',default='chemical',choices=['chemical','electrical'])
    parser.add_argument('--seed',default='rcg005-procedural-neural-v1')
    parser.add_argument('--fixture',action='store_true',
                        help='explicitly allow locally modified source; external SHA-256 still required')
    parser.add_argument('--certificate',type=Path)
    parser.add_argument('--result',type=Path)
    parser.add_argument('--tick',type=int,default=2**56+73)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    model=load_model(args.source,args.expected_source_sha256,tuple(args.coordinates),
                     seed=args.seed,fixture=args.fixture,kind=args.kind)
    if args.mode=='prepare':
        artifact=prepare_capsule(model)
    else:
        if args.certificate is None:raise TemporalGroundRefused('receiver requires source capsule')
        capsule=read_json_strict(args.certificate)
        certificate=verify_capsule(model,capsule)
        if args.mode=='verify':
            artifact=navigate(model,certificate,args.tick,trusted_certificate=True)
        else:
            if args.result is None:raise TemporalGroundRefused('receiver requires result artifact')
            artifact=read_json_strict(args.result)
            verify_result(model,certificate,artifact)
    write_json(args.out,artifact)
    print(json.dumps({'mode':args.mode,'source_blob':model.operator.blob,
                      'model_digest':model.fingerprint,
                      'output_digest':hash_object(artifact),'path':str(args.out)},sort_keys=True))

if __name__=='__main__':
    try:
        main()
    except (TemporalGroundRefused,ValueError,KeyError,TypeError) as exc:
        parser_error=f'REFUSED: {exc}'
        import sys
        print(parser_error,file=sys.stderr)
        raise SystemExit(2)
