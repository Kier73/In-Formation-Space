"""HTTP GET as an actual, bounded signed observation path (PGT-004).

The HTTP process runs a declared source observer; an unauthenticated HTTP GET
is *not* authority and each output is independently signed by an enrolled key.
This loopback-only test does not claim HTTPS/mTLS, global internet execution,
or proof that the source is truthful.
"""
from __future__ import annotations
import argparse,base64,hashlib,json,secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cognitive_grounds import canonical
from observer_worker import _sign,key_id
from query_worker import KIND,REPLY

class Server(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=True

def create(name:str,key_file:Path,source_file:Path,fault:int=-1):
    src=json.loads(source_file.read_bytes())
    assert set(src)=={'schema','root','outputs','salt'} and src['schema']=='ifs.pgt003.query.source.v1'
    assert len(src['outputs'])==8 and all(type(x)==int and x in (0,1) for x in src['outputs'])
    assert type(src['salt'])==str and len(src['salt'])==64
    assert src['root']==hashlib.sha256(canonical({k:v for k,v in src.items() if k!='root'})).hexdigest()
    key=serialization.load_pem_private_key(key_file.read_bytes(),password=None)
    assert isinstance(key,Ed25519PrivateKey)
    boot=secrets.token_hex(16)
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            try:
                parsed=urlsplit(self.path)
                params=parse_qs(parsed.query,keep_blank_values=True,strict_parsing=True)
                if parsed.path!='/v1/observe' or set(params)!={'request'} or len(params['request'])!=1 or parsed.fragment:
                    return self.send_error(404)
                token=params['request'][0]
                if len(token)>2048 or any(ch not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-' for ch in token):
                    return self.send_error(400)
                payload=base64.urlsafe_b64decode(token+'='*((-len(token))%4))
                if len(payload)>1024:return self.send_error(413)
                req=json.loads(payload)
                if canonical(req)!=payload or type(req)!=dict or set(req)!={'kind','host','nonce','root','coordinate'} or req['kind']!=KIND or req['host']!=name or req['root']!=src['root'] or type(req['nonce'])!=str or len(req['nonce'])!=32 or type(req['coordinate'])!=int or not 0<=req['coordinate']<8:
                    return self.send_error(400)
                q=req['coordinate']; value=src['outputs'][q]^int(q==fault)
                body={'kind':REPLY,'host':name,'nonce':req['nonce'],'root':src['root'],'coordinate':q,'value':value,
                      'request_digest':hashlib.sha256(canonical(req)).hexdigest(),'boot':boot,'key_id':key_id(key)}
                raw=canonical(_sign(key,body))
                self.send_response(200);self.send_header('Content-Type','application/vnd.ifs.signed-observation+json')
                self.send_header('Content-Length',str(len(raw)))
                self.send_header('ETag','"'+hashlib.sha256(raw).hexdigest()+'"')
                self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(raw)
            except (ValueError,KeyError,TypeError,OverflowError):self.send_error(400)
        def do_POST(self):self.send_error(405)
        def log_message(self,*args):pass
    return Server(('127.0.0.1',0),Handler)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--name',required=True);ap.add_argument('--key',required=True,type=Path)
    ap.add_argument('--source',required=True,type=Path);ap.add_argument('--fault',type=int,default=-1)
    a=ap.parse_args();s=create(a.name,a.key,a.source,a.fault)
    print('LISTEN_PORT='+str(s.server_port),flush=True)
    try:s.serve_forever()
    finally:s.server_close()

if __name__=='__main__':main()
