"""RCG-006: portable source-bound observer quotient for separate receiver processes.

No new transport, trust root or persistence authority: this is an application
capsule for existing E-CPU authenticated paths and source-owned verification.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any
from connectome_ground import ConnectomeGround
from observer_quotient import (
    ExpandedSyntheticGround, QuotientRefused,discover,verify,quotient_at,
    verify_query,
)
from temporal_ground import hash_object

MAX_DOCUMENT=1_000_000
SHA256=re.compile(r'[0-9a-f]{64}\Z')


def _uniques(pairs):
    result={}
    for k,v in pairs:
        if k in result:
            raise QuotientRefused('duplicate JSON key in untrusted certificate')
        result[k]=v
    return result


def _read(path:Path)->dict:
    raw=path.read_bytes()
    if not 1<=len(raw)<=MAX_DOCUMENT:
        raise QuotientRefused('untrusted portable document outside byte budget')
    try:
        doc=json.loads(raw,object_pairs_hook=_uniques,
                       parse_constant=lambda _x: (_ for _ in ()).throw(QuotientRefused('non-finite JSON token')))
    except (UnicodeError,json.JSONDecodeError) as err:
        raise QuotientRefused('invalid UTF-8 JSON capsule') from err
    if type(doc) is not dict:
        raise QuotientRefused('expected a canonical JSON object')
    return doc


def _write(path:Path,doc:dict)->None:
    raw=(json.dumps(doc,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False)+'\n').encode()
    if len(raw)>MAX_DOCUMENT:
        raise QuotientRefused('portable capsule exceeds resource cap')
    if path.exists():
        raise QuotientRefused('output already exists; immutable capsule not overwritten')
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(raw)


def _source(path:Path,expected_sha256:str,fixture:bool)->ConnectomeGround:
    if type(expected_sha256) is not str or SHA256.fullmatch(expected_sha256) is None:
        raise QuotientRefused('receiver requires source SHA-256 outside the document')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise QuotientRefused('receiver-held source SHA-256 differs from original bytes')
    return ConnectomeGround.from_csv(raw,require_original=not fixture)


def _expand(source:ConnectomeGround,certificate:dict)->ExpandedSyntheticGround:
    if type(certificate) is not dict or type(certificate.get('expanded')) is not dict:
        raise QuotientRefused('missing source-bound expansion description')
    config=certificate['expanded']
    try:
        return ExpandedSyntheticGround(source,groups=config['groups'],
                                      copies=config['copies'],seed=config['seed'])
    except (KeyError,TypeError,ValueError) as err:
        raise QuotientRefused('unadmitted source expansion') from err


def main(argv=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['train','verify','query','replay'])
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--expected-source-sha256',required=True)
    parser.add_argument('--fixture',action='store_true',help='explicit non-original test mode')
    parser.add_argument('--certificate',type=Path)
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--expected-expansion-digest')
    parser.add_argument('--groups',type=int,default=16)
    parser.add_argument('--copies',type=int,default=256)
    parser.add_argument('--seed',type=int,default=73)
    parser.add_argument('--micro-source',type=int,default=0)
    parser.add_argument('--tick',type=int,default=2**56+73)
    parser.add_argument('--depth',type=int,default=6)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args(argv)
    ground=_source(args.source,args.expected_source_sha256,args.fixture)
    if args.action=='train':
        op=ExpandedSyntheticGround(ground,groups=args.groups,copies=args.copies,seed=args.seed)
        cert=discover(op)
        verify(op,cert,replay_observations=True)
        report=cert
    else:
        if args.certificate is None:
            raise QuotientRefused('receiver requires source-bound certificate file')
        cert=_read(args.certificate)
        op=_expand(ground,cert)
        if args.expected_expansion_digest is not None and args.expected_expansion_digest!=op.fingerprint:
            raise QuotientRefused('receiver-owned expansion identity differs')
        audited=verify(op,cert,replay_observations=True)
        if args.action=='verify':
            report={'schema':'ifs.rcg006.receiver-source-verification.v1',
                    'source_ground':ground.fingerprint,'expanded_digest':op.fingerprint,
                    'certificate_digest':cert['digest'],'checked_micro_columns':op.n,
                    'checked_micro_edges':8*op.n,'checked_observation_rows':cert['training_horizon']+1,
                    'class_count':cert['class_count'],'status':'exact-intertwining-verified-not-transport-authority'}
            report['digest']=hash_object(report)
        elif args.action=='query':
            report=quotient_at(op,cert,args.micro_source,args.tick,depth=args.depth,trusted=audited)
            verify_query(op,cert,report,trusted=audited)
        else:
            if args.receipt is None:
                raise QuotientRefused('replay requires a received observation')
            observed=_read(args.receipt)
            verify_query(op,cert,observed,trusted=audited)
            report={'schema':'ifs.rcg006.replay-verdict.v1',
                    'source_ground':ground.fingerprint,'expanded_digest':op.fingerprint,
                    'certificate_digest':cert['digest'],'observation_digest':observed['digest'],
                    'status':'independently-recomputed-no-network-authentication'}
            report['digest']=hash_object(report)
    _write(args.out,report)
    return 0


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (QuotientRefused,ValueError,KeyError,TypeError) as err:
        print('REFUSED:',err,file=sys.stderr)
        raise SystemExit(2)
