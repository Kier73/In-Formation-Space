"""Audited direct HTTP retrieval of already-trained model bytes through two child processes."""
from __future__ import annotations
import hashlib
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import numpy as np
import torch
from procedural_ground_training import SCHEMA,canonical, dataset
from train_ground_model import restore
from http_artifact_path import get_verified,Refused

HERE=Path(__file__).resolve().parent

def audit():
    d=HERE/'results';raw=(d/'ground_student.npz').read_bytes(); sha=hashlib.sha256(raw).hexdigest()
    source_model,_=restore(d)
    data,_,_=dataset(7001,22)
    with torch.no_grad():
        expected=source_model(torch.tensor(data)).numpy().copy()
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp)
        processes=[]
        for n in ('a','b'):
            p=root/n; (p/'objects').mkdir(parents=True)
            (p/'objects'/(sha+'.npz')).write_bytes(raw)
            child=subprocess.Popen([sys.executable,'-u',str(HERE/'http_artifact_path.py'),'--root',str(p)],
                                  stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            assert child.stdout
            announced=child.stdout.readline().strip()
            if not announced.startswith('LISTEN_PORT='):
                raise RuntimeError('HTTP origin failed to start')
            processes.append((n,p,child,'http://127.0.0.1:'+announced.split('=',1)[1]+'/'))
        routes=[item[3] for item in processes];phase={}
        try:
            def attempt(label):
                start=time.perf_counter()
                payload,origin,failures=get_verified(routes,sha)
                receiver=root/'receiver';receiver.mkdir(exist_ok=True)
                (receiver/'manifest.json').write_bytes((d/'manifest.json').read_bytes())
                (receiver/'ground_student.npz').write_bytes(payload)
                receiver_model,_=restore(receiver)
                with torch.no_grad():
                    observed=receiver_model(torch.tensor(data)).numpy()
                if not np.array_equal(expected,observed):
                    raise RuntimeError('receiver neural predictions differ')
                phase[label]={'selected_origin':'a' if origin==routes[0] else 'b',
                              'failed_origins_count':len(failures),
                              'received_model_bytes':len(payload),
                              'test_inputs':len(data),'neural_logits_identical':True,
                              'elapsed_ms':round((time.perf_counter()-start)*1000,3)}
            attempt('both_origins')
            processes[0][2].kill();processes[0][2].wait(timeout=3)
            attempt('first_origin_killed')
            (processes[1][1]/'objects'/(sha+'.npz')).write_bytes(b'corrupted')
            try:get_verified(routes,sha)
            except Refused:
                phase['both_inaccessible_or_corrupt']={'status':'REFUSED'}
            else:raise RuntimeError('corrupted model was accepted')
        finally:
            for _,_,child,_ in processes:
                if child.poll() is None:child.kill()
                child.wait(timeout=3)
                if child.stdout:child.stdout.close()
                if child.stderr:child.stderr.close()
    report={'schema':SCHEMA+'.http-audit','origin_class':'two distinct loopback HTTP server processes, one physical host',
            'model_bytes_sha256':sha, 'manifest_sha256':hashlib.sha256((d/'manifest.json').read_bytes()).hexdigest(),
            'phases':phase, 'public_host_or_tls_claim':False,'model_trained_by_http':False,
            'verification':'local receiver pinned bytes + known fixed neural architecture'}
    (d/'http-audit.json').write_bytes(canonical(report))
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':audit()
