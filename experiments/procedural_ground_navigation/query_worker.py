"""PGT-003 narrow signed finite-feature observer using the COG-009 signer.

Not a replacement for authenticated E-CPU Transit or IOS-003 mTLS. The worker
holds source data and its signing key; the receiver sees only selected reads.
"""
from __future__ import annotations
import argparse,hashlib,json,secrets,sys
from pathlib import Path
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_grounds import canonical
from observer_worker import _sign,key_id

KIND='ifs.pgt003.query.request.v1'
REPLY='ifs.pgt003.query.signed.v1'

def main():
    p=argparse.ArgumentParser();p.add_argument('--name',required=True)
    p.add_argument('--key',required=True,type=Path);p.add_argument('--source',required=True,type=Path)
    p.add_argument('--fault',type=int,default=-1)
    a=p.parse_args();raw=a.source.read_bytes();src=json.loads(raw)
    if set(src)!={'schema','root','outputs','salt'} or src['schema']!='ifs.pgt003.query.source.v1' or len(src['outputs'])!=8 or any(type(x)!=int or x not in (0,1) for x in src['outputs']):
        raise ValueError('source contract invalid')
    if type(src['salt'])!=str or len(src['salt'])!=64 or any(z not in '0123456789abcdef' for z in src['salt']):raise ValueError('source salt invalid')
    if src['root']!=hashlib.sha256(canonical({'schema':src['schema'],'outputs':src['outputs'],'salt':src['salt']})).hexdigest():raise ValueError('source root mismatch')
    key=serialization.load_pem_private_key(a.key.read_bytes(),password=None)
    if not isinstance(key,Ed25519PrivateKey):raise ValueError('Ed25519 required')
    boot=secrets.token_hex(16)
    for raw in sys.stdin.buffer:
        req=json.loads(raw)
        if type(req)!=dict or set(req)!={'kind','host','nonce','root','coordinate'} or req['kind']!=KIND or req['host']!=a.name or req['root']!=src['root'] or type(req['nonce'])!=str or len(req['nonce'])!=32 or type(req['coordinate'])!=int or not 0<=req['coordinate']<8:raise ValueError('invalid bounded query')
        q=req['coordinate'];value=int(src['outputs'][q]) ^ int(q==a.fault)
        body={'kind':REPLY,'host':a.name,'nonce':req['nonce'],'root':src['root'],
              'coordinate':q,'value':value,'request_digest':hashlib.sha256(canonical(req)).hexdigest(),
              'boot':boot,'key_id':key_id(key)}
        sys.stdout.buffer.write(canonical(_sign(key,body))+b'\n');sys.stdout.buffer.flush()

if __name__=='__main__':main()
