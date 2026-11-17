"""PGT-005 supervised *separate-process* native E-CPU measurement experiment.

Requires E-CPU (PR169 fix), torch, numpy, cryptography, real localhost TCP/TLS.
Three independently enrolled signing subprocesses are behind a native provider
which is itself an independent OS process from the receiver. No trusted source
law is inferred from the signature count; Ground admission remains false.
"""
from __future__ import annotations
import argparse,datetime,hashlib,json,os,secrets,selectors,signal,subprocess,sys,time
from pathlib import Path
from cryptography import x509
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
from cognitive_grounds import canonical
from decision_experiment import H

ROOT=Path(__file__).resolve().parent


def make_certs(path:Path)->None:
    path.mkdir(parents=True,exist_ok=True)
    now=datetime.datetime.now(datetime.timezone.utc)
    key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    issuer=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'PGT005-Test-CA')])
    ca=(x509.CertificateBuilder().subject_name(issuer).issuer_name(issuer)
        .public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now-datetime.timedelta(hours=1))
        .not_valid_after(now+datetime.timedelta(days=2))
        .add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,
            key_encipherment=False,data_encipherment=False,key_agreement=False,
            key_cert_sign=True,crl_sign=True,encipher_only=False,decipher_only=False),critical=True)
        .sign(key,hashes.SHA256()))
    (path/'ca.pem').write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    for role,domain in [('provider','provider-b.fabric.test'),('receiver','receiver-a.fabric.test')]:
        priv=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,domain)])
        cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(issuer)
            .public_key(priv.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now-datetime.timedelta(hours=1))
            .not_valid_after(now+datetime.timedelta(days=1))
            .add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(domain)]),critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH,
                                                   ExtendedKeyUsageOID.CLIENT_AUTH]),critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True,content_commitment=False,
                key_encipherment=True,data_encipherment=False,key_agreement=False,
                key_cert_sign=False,crl_sign=False,encipher_only=False,decipher_only=False),critical=True)
            .sign(key,hashes.SHA256()))
        (path/(role+'.pem')).write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        k=path/(role+'.key')
        k.write_bytes(priv.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        k.chmod(0o600)


def launch_provider(root:Path,index:int,source_salt:str,fault:int|None,source_bits:str|None=None)->tuple[subprocess.Popen,int,dict]:
    cmd=[sys.executable,str(ROOT/'native_provider.py'),'--root',str(root),'--index',str(index),
         '--salt',source_salt]
    if fault is not None:cmd+=['--fault-coordinate',str(fault)]
    if source_bits is not None:cmd+=['--source-bits',source_bits]
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=False,bufsize=0)
    try:
        assert proc.stdout is not None
        with selectors.DefaultSelector() as sel:
            sel.register(proc.stdout,selectors.EVENT_READ)
            if not sel.select(12):raise RuntimeError('native provider failed to announce bound TLS port')
        line=proc.stdout.readline(2048).decode('utf8').strip()
        if not line.startswith('READY '):raise RuntimeError('unexpected provider greeting: '+line)
        ready=json.loads(line[6:]);port=ready['port']
        if not isinstance(port,int) or port<1 or port>65535:raise ValueError('invalid provider port')
        return proc,port,ready
    except BaseException:
        proc.kill();proc.wait(timeout=5)
        raise


def verify(root:Path,expected_head:str|None=None,expected_root:str|None=None)->dict:
    """Fresh-process verifier; separately pinned signer roster and final head."""
    from path_navigator import recover_paths
    from native_contract import contract_at
    from mailcpu.observer_orbit import ObserverReceipt,verify_observer_receipt
    trust=json.loads((root/'evidence/trust.json').read_bytes())
    ledger=json.loads((root/'evidence/bundle.json').read_bytes())
    if expected_head is not None and trust['head']!=expected_head:raise ValueError('external signature head mismatch')
    if expected_root is not None and trust['source_root']!=expected_root:raise ValueError('external source identity mismatch')
    signed=recover_paths(ledger,trust)
    received=json.loads((root/'receiver-report.json').read_bytes())
    provider=json.loads((root/'provider-report.json').read_bytes())
    if provider['source_root']!=trust['source_root'] or signed['admitted'] is not False:
        raise ValueError('source provenance / Ground-admission class differs')
    if received['pinned_source_root']!=trust['source_root']:
        raise ValueError('receiver requested different source root')
    if received['terminal_status'] not in ('UNKNOWN','WITNESSED_NOT_GROUND_ADMITTED'):
        raise ValueError('unknown terminal evidence status')
    recorded={}
    for r in received['native_receipts']:
        q=r['coordinate']; value=r['value']
        rec=ObserverReceipt.from_dict(r['native_receipt'])
        if not verify_observer_receipt(contract_at(q,trust['source_root']),rec) or rec.projection!=value or rec.operation_id != 'q'+str(q):
            raise ValueError('native observation receipt semantics differ')
        if signed['qualified_observations'].get(q)!=value:
            raise ValueError('native mTLS reading disagrees with retained signed source')
        if q in recorded and recorded[q]!=value:raise ValueError('receiver reinterpreted same coordinate')
        recorded[q]=value
    for q,v in received['readings'].items():
        if recorded.get(int(q))!=v:raise ValueError('receiver used unsubstantiated observation')
    if received['terminal_status']=='WITNESSED_NOT_GROUND_ADMITTED':
        t=received['intention_coordinate']
        if received['result']!=recorded[t]:raise ValueError('unwitnessed terminal value')
    result={'schema':'ifs.pgt005.fresh-recovery.v1','signature_count':signed['signed_receipt_count'],
            'http_signed_reads':signed['http_reads'],'stdio_signed_reads':signed['stdio_reads'],
            'native_receipt_count':len(received['native_receipts']),
            'native_receipt_values_verified_against_signed_ensemble':len(recorded),
            'source_calls':0,'ground_admitted':False,
            'source_root':trust['source_root'],'high_water_head':trust['head'],
            'terminal_status':received['terminal_status']}
    (root/'independent-verification.json').write_bytes(canonical(result))
    return result


def run(root:Path,index:int=12,target:int=6,fault:int|None=None,source_bits:str|None=None)->dict:
    root.mkdir(parents=True,exist_ok=True)
    make_certs(root/'tls')
    source_salt=secrets.token_hex(32)
    actual=([int(v) for v in source_bits] if source_bits is not None else H[index].tolist())
    expected_source={'schema':'ifs.pgt003.query.source.v1',
                     'outputs':list(map(int,actual)),'salt':source_salt}
    expected_root=hashlib.sha256(canonical(expected_source)).hexdigest()
    provider,port,ready=launch_provider(root,index,source_salt,fault,source_bits)
    if ready['source_root']!=expected_root:
        provider.kill();provider.communicate(timeout=5)
        raise ValueError('provider substituted supervisor-pinned source root')
    receiver_stdout='';receiver_stderr='';returncode=None
    try:
        cmd=[sys.executable,str(ROOT/'native_receiver.py'),'--root',str(root),'--port',str(port),
             '--target',str(target),'--source-root',expected_root]
        if fault is not None:cmd+=['--mode','fail-then-recover']
        rec=subprocess.run(cmd,capture_output=True,text=True,timeout=35)
        returncode=rec.returncode;receiver_stdout=rec.stdout;receiver_stderr=rec.stderr
    finally:
        provider.terminate()
        try:out,err=provider.communicate(timeout=9)
        except subprocess.TimeoutExpired:
            provider.kill();out,err=provider.communicate(timeout=5)
        (root/'provider-stderr.log').write_bytes(err)
        (root/'receiver-stderr.log').write_text(receiver_stderr)
    if returncode!=0:
        raise RuntimeError('native receiver failed: '+receiver_stderr[-1600:]+'; provider: '+err.decode(errors='replace')[-1600:])
    if provider.returncode not in (0,None):
        raise RuntimeError('native provider failed: '+err.decode(errors='replace')[-1700:])
    r=verify(root,expected_root=expected_root)
    r['separate_provider_process_pid']=ready['server_pid'];r['receiver_result']=json.loads(receiver_stdout)
    r['native_provider']=json.loads((root/'provider-report.json').read_bytes())
    r['injected_fault']=fault is not None
    r['synthetic_out_of_family']=source_bits is not None
    (root/'audit.json').write_bytes(canonical(r))
    return r

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True)
    p.add_argument('--source-index',type=int,default=12);p.add_argument('--target',type=int,default=6)
    p.add_argument('--fault-coordinate',type=int);p.add_argument('--source-bits')
    p.add_argument('--verify',action='store_true');p.add_argument('--expected-head');p.add_argument('--expected-root')
    a=p.parse_args();res=(verify(a.root,a.expected_head,a.expected_root) if a.verify
        else run(a.root,a.source_index,a.target,a.fault_coordinate,a.source_bits))
    print(json.dumps(res,indent=2))
