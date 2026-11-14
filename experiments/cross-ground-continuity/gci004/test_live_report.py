"""Adversarial verification against the *actual* mTLS-hosted report artifact.

Run in the independent GCI-004 audit job after executing the live network.
"""
from __future__ import annotations
import argparse
import copy
from pathlib import Path
import fabric_contract as c


def run(directory: Path) -> None:
    path=directory/'gci004-network.json'
    original=c.cag.read(path)
    baseline=c.verified_report(directory)
    assert baseline['signed_observations']==2
    variants=[]
    def tweak(label,fn):
        value=copy.deepcopy(original)
        fn(value)
        value['report_digest']=c.jdigest({k:v for k,v in value.items() if k!='report_digest'})
        variants.append((label,value))
    tweak('forged signed value',lambda r:r['requests'][0]['payload'].__setitem__('value',99))
    tweak('replayed request challenge',lambda r:r['requests'][1]['request'].__setitem__(
         'challenge',r['requests'][0]['request']['challenge']))
    tweak('forged signed request authority',lambda r:r['requests'][0]['request']['binding'].__setitem__(
         'ground_fingerprint','0'*64))
    tweak('wrong host',lambda r:r['requests'][0].__setitem__('peer_id','observer-c'))
    tweak('wrong leaf certificate',lambda r:r['discovery'][0].__setitem__(
         'certificate_pem',r['discovery'][1]['certificate_pem']))
    tweak('false negative claim',lambda r:r.__setitem__('bad_hostname_refused',False))
    tweak('forged result',lambda r:r['realization'][0].__setitem__('result',99))
    tweak('extra feature',lambda r:r['measurements'][3]['readings'].append({'name':'parity','value':0}))
    tweak('altered symbol cost',lambda r:r['discovery'][0]['snapshot']['hosts'][0]['costs'][0].__setitem__('amount',9))
    try:
        for label,data in variants:
            c.cag.persist(path,data)
            try: c.verified_report(directory)
            except Exception: pass
            else: raise AssertionError('auditor accepted '+label)
    finally:
        c.cag.persist(path,original)
    print('GCI-004: live positive audit plus',len(variants),'resealed adversarial mutations refused')


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--directory',type=Path,required=True)
    args=p.parse_args()
    run(args.directory)


if __name__=='__main__': main()
