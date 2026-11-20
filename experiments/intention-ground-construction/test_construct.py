"""Finite differential and cross-language tests for intention-built state-space Grounds."""
import copy
import itertools
import json
from pathlib import Path
import random
import shutil
import subprocess
import tempfile
import unittest

from construct import (ConstructionError, digest, execute, matches, navigate_repeat,
                       normalize_intention, parse_language, synthesize)

HERE=Path(__file__).parent
INTENT=json.loads((HERE/'intention.json').read_text(encoding='utf8'))


def node_check(intent,receipt):
    with tempfile.TemporaryDirectory() as folder:
        a,b=Path(folder)/'intent.json',Path(folder)/'receipt.json'
        a.write_text(json.dumps(intent),encoding='utf8')
        b.write_text(json.dumps(receipt),encoding='utf8')
        return subprocess.run(['node',str(HERE/'verify.mjs'),str(a),str(b)],
                              text=True,capture_output=True)


class ConstructTests(unittest.TestCase):
    def test_constructor_produces_canonical_minimal_machine(self):
        receipt=synthesize(INTENT)
        p=receipt['payload'];ground=p['ground']
        self.assertEqual(p['status'],'realized_under_declared_capacity')
        self.assertEqual(ground['state_count'],3)
        self.assertEqual(ground['transitions'],[[1,0],[1,2],[1,0]])
        self.assertEqual(ground['accepting'],[False,False,True])
        self.assertEqual(p['minimality_certificate']['reachable_prefixes'],
                         [[],['0'],['0','1']])
        self.assertEqual(len(p['minimality_certificate']['distinguishing_suffixes']),3)
        self.assertEqual(receipt,synthesize(copy.deepcopy(INTENT)))

    def test_all_short_words_match_independent_description(self):
        g=synthesize(INTENT)['payload']['ground']
        regex=parse_language(INTENT['language'],set(INTENT['alphabet']))
        for length in range(8):
            for w in itertools.product(INTENT['alphabet'],repeat=length):
                self.assertEqual(execute(g,w)[1],matches(regex,w),w)

    def test_billion_billion_billion_navigation_no_history(self):
        ground=synthesize(INTENT)['payload']['ground']
        self.assertEqual(navigate_repeat(ground,'0',10**30,suffix=['1']),(2,True))
        for count in range(100):
            self.assertEqual(navigate_repeat(ground,'0',count,prefix=['1'],suffix=['1']),
                             execute(ground,['1']+['0']*count+['1']))
        for wrong in (-1,1.0,True):
            with self.assertRaises(ConstructionError):
                navigate_repeat(ground,'0',wrong)

    def test_necessary_state_lower_bound_not_search_failure(self):
        input=copy.deepcopy(INTENT);input['max_states']=2
        p=synthesize(input)['payload']
        self.assertEqual(p['status'],'insufficient_declared_state_capacity')
        self.assertEqual(p['ground']['state_count'],3)
        self.assertEqual(len(p['minimality_certificate']['distinguishing_suffixes']),3)
        self.assertEqual(p['authority'],'mathematical_only_no_host_execution_rights')

    def test_contradictory_required_word_gives_direct_counterexample(self):
        input=copy.deepcopy(INTENT);input['required'].append(['0'])
        p=synthesize(input)['payload']
        self.assertEqual(p['status'],'incompatible_language_constraints')
        self.assertEqual(p['witness'],dict(word=['0'],declared='required',
                                          required_acceptance=True,language_acceptance=False))

    def test_contradictory_forbidden_word_gives_direct_counterexample(self):
        input=copy.deepcopy(INTENT);input['forbidden'].append(['0','1'])
        p=synthesize(input)['payload']
        self.assertEqual(p['status'],'incompatible_language_constraints')
        self.assertEqual(p['witness']['declared'],'forbidden')

    def test_malformed_intentions_rejected(self):
        invalid=[]
        for value in (False,0,0.0,33):
            x=copy.deepcopy(INTENT);x['max_states']=value;invalid.append(x)
        x=copy.deepcopy(INTENT);x['alphabet']=['1','0'];invalid.append(x)
        x=copy.deepcopy(INTENT);x['language']={'op':'symbol','value':[]};invalid.append(x)
        x=copy.deepcopy(INTENT);x['language']={'op':'star','arg':{'op':'epsilon','code':'oops'}};invalid.append(x)
        x=copy.deepcopy(INTENT);x['required']=[['X']];invalid.append(x)
        x=copy.deepcopy(INTENT);x['required']=[['1'],['1']];invalid.append(x)
        x=copy.deepcopy(INTENT);x['authority']='host';invalid.append(x)
        for invalid_intention in invalid:
            with self.subTest(spec=invalid_intention),self.assertRaises(ConstructionError):
                normalize_intention(invalid_intention)

    def test_random_regular_languages_against_derivative_oracle(self):
        randomizer=random.Random(610011)
        atom=[{'op':'symbol','value':'0'},{'op':'symbol','value':'1'},
              {'op':'epsilon'},{'op':'empty'}]
        for _ in range(45):
            def gen(depth):
                if depth==0 or randomizer.randrange(3)==0:
                    return randomizer.choice(atom)
                op=randomizer.choice(['concat','alt','star'])
                if op=='star': return {'op':op,'arg':gen(depth-1)}
                return {'op':op,'args':[gen(depth-1),gen(depth-1)]}
            expr=gen(3)
            intent=copy.deepcopy(INTENT)
            intent.update(language=expr,required=[],forbidden=[],max_states=32)
            p=synthesize(intent)['payload']
            self.assertNotEqual(p['status'],'budget_exhausted')
            g=p['ground'];regex=parse_language(expr,set(intent['alphabet']))
            for l in range(7):
                for w in itertools.product(intent['alphabet'],repeat=l):
                    self.assertEqual(execute(g,w)[1],matches(regex,w),(expr,w))


@unittest.skipUnless(shutil.which('node'),'Node.js receiver unavailable')
class IndependentReceiverTests(unittest.TestCase):
    def test_receiver_accepts_mathematical_realization(self):
        p=node_check(INTENT,synthesize(INTENT))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['minimal_states'],3)

    def test_receiver_accepts_certified_capacity_obstruction(self):
        i=copy.deepcopy(INTENT);i['max_states']=2
        p=node_check(i,synthesize(i))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['status'],
                         'insufficient_declared_state_capacity')

    def test_receiver_accepts_direct_contradiction(self):
        i=copy.deepcopy(INTENT);i['forbidden'].append(['0','1'])
        p=node_check(i,synthesize(i))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(json.loads(p.stdout)['status'],
                         'incompatible_language_constraints')

    def test_receiver_refuses_self_rehashed_fabricated_ground(self):
        r=synthesize(INTENT)
        r['payload']['ground']['transitions'][0][0]=0
        g=r['payload']['ground']
        g['ground_sha256']=digest({k:v for k,v in g.items() if k!='ground_sha256'})
        r['sha256']=digest(r['payload'])
        p=node_check(INTENT,r)
        self.assertNotEqual(p.returncode,0)
        self.assertIn('REFUSED',p.stderr)

    def test_receiver_refuses_forged_minimality_certificate(self):
        r=synthesize(INTENT)
        r['payload']['minimality_certificate']['distinguishing_suffixes'][0]['suffix']=[]
        r['sha256']=digest(r['payload'])
        self.assertNotEqual(node_check(INTENT,r).returncode,0)

    def test_receiver_refuses_rehashed_authority_grant(self):
        r=synthesize(INTENT)
        r['payload']['authority']='run_on_any_network_host'
        r['sha256']=digest(r['payload'])
        self.assertNotEqual(node_check(INTENT,r).returncode,0)

    def test_receiver_refuses_swapped_trusted_intention(self):
        r=synthesize(INTENT)
        other=copy.deepcopy(INTENT);other['max_states']=2
        self.assertNotEqual(node_check(other,r).returncode,0)

    def test_large_coordinate_navigation_matches_independent_js(self):
        receipt=synthesize(INTENT)
        g=receipt['payload']['ground']
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'ground.json'
            path.write_text(json.dumps(g),encoding='utf8')
            program=(
                'import {navigateRepeat} from '+json.dumps((HERE/'verify.mjs').as_uri())+';'
                'import {readFileSync} from "node:fs";'
                'const g=JSON.parse(readFileSync(process.argv[1],"utf8"));'
                'console.log(JSON.stringify(navigateRepeat(g,"0",10n**30n,[],["1"])));'
            )
            result=subprocess.run(['node','--input-type=module','-e',program,str(path)],
                                  capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(json.loads(result.stdout),
                             dict(zip(('state','accepting'),navigate_repeat(g,'0',10**30,suffix=['1']))))

    def test_receiver_independent_equivalence_varied_regular_languages(self):
        for expr in (
            {'op':'epsilon'}, {'op':'empty'},
            {'op':'star','arg':{'op':'symbol','value':'1'}},
            {'op':'alt','args':[{'op':'symbol','value':'0'},
                                {'op':'symbol','value':'1'}]},
            {'op':'concat','args':[{'op':'star','arg':{'op':'symbol','value':'0'}},
                                   {'op':'symbol','value':'1'}]},
        ):
            i=copy.deepcopy(INTENT);i.update(language=expr,required=[],forbidden=[],max_states=32)
            r=synthesize(i);p=node_check(i,r)
            self.assertEqual(p.returncode,0,repr(expr)+p.stderr)


if __name__=='__main__':unittest.main()
