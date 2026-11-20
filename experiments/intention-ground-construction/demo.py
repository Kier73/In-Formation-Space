"""Generate three portable intention-ground receipts and one vast coordinate query."""
import argparse
import copy
import json
from pathlib import Path
from construct import navigate_repeat, synthesize


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,default=Path('build/igc001'))
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    base=json.loads(Path(__file__).with_name('intention.json').read_text(encoding='utf8'))
    too_small=copy.deepcopy(base);too_small['max_states']=2
    conflict=copy.deepcopy(base);conflict['required'].append(['0'])
    summary={'schema':'ifs.igc001.demonstration.v1','examples':{}}
    for name,intent in [('realized',base),('capacity-obstruction',too_small),('contradiction',conflict)]:
        receipt=synthesize(intent)
        (args.output/(name+'.intention.json')).write_text(json.dumps(intent,indent=2)+'\n',encoding='utf8')
        (args.output/(name+'.receipt.json')).write_text(json.dumps(receipt,indent=2)+'\n',encoding='utf8')
        state=receipt['payload'].get('ground',{}).get('state_count')
        summary['examples'][name]={'status':receipt['payload']['status'],
                                    'state_count':state,'receipt_sha256':receipt['sha256']}
    ground=synthesize(base)['payload']['ground']
    coord=10**30
    state,accepts=navigate_repeat(ground,'0',coord,suffix=['1'])
    summary['navigation']={'coordinate_repeat_count':str(coord),'symbol':'0',
                           'suffix':['1'],'state':state,'accepting':accepts,
                           'claimed_execution':'mathematical_dfa_only'}
    (args.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,sort_keys=True))


if __name__=='__main__':
    main()
