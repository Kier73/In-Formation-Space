"""COG-009 separate-process test observer. Not a replacement for E-CPU Transit.

The operator provisions a host-specific Ed25519 private key in a separate file;
only signed membership observations leave the process. A source may still lie.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import json
import os
import sys
import uuid
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_grounds import canonical
from predictive_state import Teacher, source_fixture

KIND = 'ifs.cog009.observer-request.v1'
RESPONSE = 'ifs.cog009.observer-signed-receipt.v1'


def key_id(key:Ed25519PrivateKey)->str:
    der=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    return hashlib.sha256(der).hexdigest()


def _sign(key:Ed25519PrivateKey,core:dict)->dict:
    return {'body':core,'signature':base64.b64encode(key.sign(hashlib.sha256(canonical(core)).digest())).decode('ascii')}


def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--id',required=True)
    ap.add_argument('--key',type=Path,required=True)
    ap.add_argument('--subjects',type=int,default=8)
    ap.add_argument('--durations',type=int,default=2)
    ap.add_argument('--named',action='store_true')
    ap.add_argument('--fault',choices=['none','target','all'],default='none')
    ap.add_argument('--sab-once',action='store_true')
    ap.add_argument('--sab-store',type=Path)
    args=ap.parse_args()
    private=serialization.load_pem_private_key(args.key.read_bytes(),password=None)
    if not isinstance(private,Ed25519PrivateKey):raise ValueError('Ed25519-only observer')
    ground,learner=source_fixture(args.subjects,args.durations)
    teacher=Teacher(ground,learner,named=args.named)
    boot=uuid.uuid4().hex
    if args.sab_once:
        if args.sab_store is None:raise ValueError('SAB qualifier requires durable state directory')
        raw=sys.stdin.buffer.readline(8193)
        if not raw or len(raw)>8192 or not raw.endswith(b'\n'):raise ValueError('invalid SAB frame')
        req=json.loads(raw)
        if (not isinstance(req,dict) or set(req)!={'kind','host','nonce','operation','payload'}
            or req['kind']!='mailcpu.sab003.request.v1' or req['host']!=args.id
            or type(req['nonce']) is not str or len(req['nonce'])!=32 or not isinstance(req['payload'],dict)):
            raise ValueError('SAB request identity invalid')
        op=req['operation'];v=req['payload'];result=None;error=None
        if op=='observe' and v=={'word':'sab003:observe:hello'}:
            result={'word_digest':hashlib.sha256(canonical(v['word'])).hexdigest()}
        elif op=='transfer' and v=={'bytes_hex':bytes(range(64)).hex()}:
            result=v
        elif op=='affine_mod' and set(v)=={'a','c','mod','x0','coordinate'}:
            # Verified independent logarithmic affine iteration, no E-CPU import in worker.
            mul,add=v['a']%v['mod'],v['c']%v['mod'];p,q=1,0;t=v['coordinate']
            while t:
                if t&1:p,q=(mul*p)%v['mod'],(mul*q+add)%v['mod']
                add,mul=(mul*add+add)%v['mod'],(mul*mul)%v['mod']
                t>>=1
            result={'value':(p*v['x0']+q)%v['mod']}
        elif op=='retain' and set(v)=={'key','value'}:
            args.sab_store.parent.mkdir(parents=True,exist_ok=True)
            temp=args.sab_store.with_suffix('.pending')
            with open(temp,'wb') as f:
                f.write(canonical(v));f.flush();os.fsync(f.fileno())
            os.replace(temp,args.sab_store)
            result={'key':v['key'],'receipt':hashlib.sha256(canonical(v['value'])).hexdigest()}
        elif op=='retrieve' and set(v)=={'key'} and args.sab_store.exists():
            stored=json.loads(args.sab_store.read_bytes())
            if stored.get('key')==v['key']:result={'key':v['key'],'value':stored['value']}
            else:error='not_found'
        elif op=='execute_source':error='unsupported'
        else:error='unsupported'
        reply={'kind':'mailcpu.sab003.reply.v1','host':args.id,'nonce':req['nonce'],
               'boot':boot,'ok':result is not None,'result':result,'error':error}
        sys.stdout.buffer.write(canonical(reply)+b'\n');sys.stdout.buffer.flush()
        return
    for raw in sys.stdin.buffer:
        try:
            if len(raw)>65536:raise ValueError('oversized input frame')
            req=json.loads(raw)
            if (not isinstance(req,dict) or set(req)!= {'kind','source_root','host','nonce','path'}
                or req['kind']!=KIND or req['host']!=args.id or req['source_root']!=teacher.source_root
                or type(req['nonce']) is not str or len(req['nonce'])!=32
                or type(req['path']) is not list or len(req['path'])>64
                or any(type(x) is not str or x not in teacher.alphabet for x in req['path'])):
                raise ValueError('invalid host/source request')
            result=[list(x) for x in teacher.query(tuple(req['path']))]
            is_target=bool(req['path'] and req['path'][-1]=='minutes' and 'mention:topic_0003' in req['path'])
            if args.fault=='all' or (args.fault=='target' and is_target):
                if result and result[-1][0]=='minutes':result[-1][1]+=1
            core={'kind':RESPONSE,'host':args.id,'source_root':teacher.source_root,
                  'nonce':req['nonce'],'request_digest':hashlib.sha256(canonical(req)).hexdigest(),
                  'path':req['path'],'outputs':result,'boot':boot,'key_id':key_id(private)}
            sys.stdout.write(json.dumps(_sign(private,core),separators=(',',':'),sort_keys=True)+'\n')
            sys.stdout.flush()
        except Exception as exc:
            print(f'COG009 worker refused frame: {type(exc).__name__}: {exc}',file=sys.stderr,flush=True)
            # Fail closed rather than constructing an unsigned error response.
            sys.exit(2)

if __name__=='__main__':main()
