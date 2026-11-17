"""PGT-002: transport learned weights through PGT-001's read-only HTTP path."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

import numpy as np
import torch

from procedural_ground_training import canonical
from cross_family_curriculum import build_examples
from train_transfer import restore
from http_artifact_path import get_verified, Refused


def audit(model_dir:Path, output:Path):
    model_dir=Path(model_dir)
    weights=(model_dir/'partial_ground_student.npz').read_bytes()
    manifest=(model_dir/'manifest.json').read_bytes()
    weight_hash=hashlib.sha256(weights).hexdigest()
    source_model,model_identity=restore(model_dir)
    x,_,_,_=build_examples(8801,19,families=('finite_automaton',),nstates=32,observed=(3,7))
    with torch.no_grad():
        expected=source_model(torch.from_numpy(x)).numpy().copy()
    processes=[];phases={}
    with tempfile.TemporaryDirectory() as td:
        base=Path(td)
        for name in ('a','b'):
            folder=base/name
            (folder/'objects').mkdir(parents=True)
            (folder/'objects'/(weight_hash+'.npz')).write_bytes(weights)
            source=Path(__file__).resolve().parent/'http_artifact_path.py'
            if not source.is_file():
                source=Path(__file__).resolve().parent.parent/'pgt001'/'http_artifact_path.py'
            command=[sys.executable,'-u',str(source), '--root',str(folder)]
            child=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            if child.stdout is None:raise RuntimeError('HTTP source missing stdout')
            announced=child.stdout.readline().strip()
            if not announced.startswith('LISTEN_PORT='):
                raise RuntimeError('HTTP source failed to launch: '+announced)
            processes.append((name,folder,child,f'http://127.0.0.1:{announced.split("=",1)[1]}/'))
        urls=[p[3] for p in processes]
        try:
            for phase in ('both_live','first_killed'):
                if phase=='first_killed':
                    processes[0][2].kill();processes[0][2].wait(timeout=4)
                start=time.perf_counter()
                fetched,origin,failures=get_verified(urls,weight_hash)
                receiver=base/'fresh-receiver'
                receiver.mkdir(exist_ok=True)
                (receiver/'manifest.json').write_bytes(manifest)
                (receiver/'partial_ground_student.npz').write_bytes(fetched)
                restored,head=restore(receiver)
                if head!=model_identity:raise RuntimeError('checkpoint model identity changed')
                with torch.no_grad():
                    observed=restored(torch.from_numpy(x)).numpy()
                if not np.array_equal(expected,observed):
                    raise RuntimeError('receiver neural outputs differ')
                phases[phase]={'selected': 'a' if origin==urls[0] else 'b',
                               'failed_origins':len(failures),'output_identical':True,
                               'source_state_inputs':len(x),'elapsed_ms':round((time.perf_counter()-start)*1000,3)}
            (processes[1][1]/'objects'/(weight_hash+'.npz')).write_bytes(b'altered model')
            try:get_verified(urls,weight_hash)
            except Refused:phases['corrupted_survivor']={'status':'REFUSED'}
            else:raise AssertionError('corrupt HTTP weights were accepted')
        finally:
            for _,_,child,_ in processes:
                if child.poll() is None:child.kill()
                child.wait(timeout=4)
                if child.stdout:child.stdout.close()
                if child.stderr:child.stderr.close()
    report={'schema':'ifs.pgt002.learned-artifact-http-proof-of-contract.v1',
            'manifest_identity':model_identity,'weights_sha256':weight_hash,
            'weights_bytes':len(weights),'origins':'two independent loopback processes on one host',
            'http_computes_model':False,'public_https_or_remote_fault_domain_claim':False,
            'phases':phases}
    output.parent.mkdir(parents=True,exist_ok=True);output.write_bytes(canonical(report))
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--model-dir',type=Path,default=Path('results'))
    p.add_argument('--output',type=Path,default=Path('results/http-transfer-report.json'))
    args=p.parse_args();audit(args.model_dir,args.output)
