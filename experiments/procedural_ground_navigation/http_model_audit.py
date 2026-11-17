"""Retain trained observation-policy weights through existing PGT-001 HTTP path."""
from __future__ import annotations
import hashlib,json,subprocess,sys,tempfile,time
from pathlib import Path
import numpy as np
import torch
from http_artifact_path import get_verified,Refused
from train_policy import restore,make_data
from decision_experiment import canonical

def audit(model_dir,output):
    model_dir=Path(model_dir);weights=(model_dir/'observer_student.npz').read_bytes();manifest=(model_dir/'manifest.json').read_bytes()
    root=hashlib.sha256(weights).hexdigest()
    model,identity=restore(model_dir)
    x,labels,_=make_data(611,22)
    with torch.no_grad():expected=model(torch.from_numpy(x)).numpy()
    home=Path(__file__).resolve().parent
    choices=(home.parent/'procedural_ground_training'/'http_artifact_path.py',
             home.parent/'pgt001'/'http_artifact_path.py',home/'http_artifact_path.py')
    source_script=next((x for x in choices if x.is_file()),None)
    if source_script is None:raise RuntimeError('PGT-001 read-only HTTP adapter is unavailable')
    processes=[];phases={}
    with tempfile.TemporaryDirectory() as temp:
        base=Path(temp)
        for name in ('a','b'):
            loc=base/name/'objects';loc.mkdir(parents=True);(loc/(root+'.npz')).write_bytes(weights)
            child=subprocess.Popen([sys.executable,'-u',str(source_script),'--root',str(loc.parent)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            marker=child.stdout.readline().strip()
            if not marker.startswith('LISTEN_PORT='):raise RuntimeError('HTTP source unavailable')
            processes.append((name,loc,child,f'http://127.0.0.1:{marker.split("=",1)[1]}/'))
        urls=[z[3] for z in processes]
        try:
            for step in ('both_live','first_killed'):
                if step=='first_killed':processes[0][2].kill();processes[0][2].wait(timeout=5)
                start=time.perf_counter();fetched,selected,failed=get_verified(urls,root)
                where=base/'receiver';where.mkdir(exist_ok=True)
                (where/'observer_student.npz').write_bytes(fetched);(where/'manifest.json').write_bytes(manifest)
                restored,other=restore(where)
                with torch.no_grad():actual=restored(torch.from_numpy(x)).numpy()
                if other['weights_sha256']!=identity['weights_sha256'] or not np.array_equal(actual,expected):raise RuntimeError('HTTP receiver parameter mismatch')
                phases[step]={'selected':'a' if selected==urls[0] else 'b','failed_origins':len(failed),
                              'identical_neural_outputs':True,'elapsed_ms':round(1000*(time.perf_counter()-start),3)}
            (processes[1][1]/(root+'.npz')).write_bytes(b'corrupted')
            try:get_verified(urls,root)
            except Refused:phases['corrupt_survivor']={'status':'REFUSED'}
            else:raise RuntimeError('artifact corruption not refused')
        finally:
            for _,_,p,_ in processes:
                if p.poll() is None:p.kill()
                p.wait(timeout=4)
                if p.stdout:p.stdout.close()
                if p.stderr:p.stderr.close()
    result={'schema':'ifs.pgt003.costed-neural-policy-http.v1','weights_sha256':root,
            'bytes':len(weights),'tested_neural_outputs':int(expected.size),
            'phases':phases,'public_network_claim':False,'server_performs_inference':False}
    Path(output).write_bytes(canonical(result));return result

if __name__=='__main__':
    from argparse import ArgumentParser
    p=ArgumentParser();p.add_argument('--results',type=Path,default=Path('results'));a=p.parse_args()
    print(json.dumps(audit(a.results,a.results/'http-audit.json'),indent=2))
