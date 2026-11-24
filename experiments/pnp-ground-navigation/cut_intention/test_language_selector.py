"""Exact CIG-006 interpretation-class and nonlinear-code regression tests."""
from __future__ import annotations
import copy,unittest
from joint_intention_ground import make_branching_source
from chain_observer_ground import _eval
from nonlinear_observer_ground import source_reduce
from language_selector import compile_language,GroundRefusal
from verify_language_selector import verify,Reject

class TemporalSelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src=make_branching_source();cls.cut=[0,1,2,3,4]
        cls.cert,_=compile_language(cls.src,cls.cut)

    def test_all_source_proved_orientations(self):
        c=self.cert
        self.assertEqual(c['candidate_class']['cartesian_options'],9)
        self.assertEqual(c['candidate_class']['conflict_free_count'],4)
        self.assertTrue(c['candidate_class']['complete_qualification'])
        self.assertEqual(c['source_model']['active_fixed_points'],8)
        self.assertTrue(verify(self.src,c,intention=c['intent']))

    def test_intention_changes_representation(self):
        c=self.cert
        self.assertEqual([x['feature_dimension'] for x in c['candidates']],[10,8,9,9])
        self.assertEqual([x['snapshot']['minimum_binary_bits'] for x in c['candidates']],[3,2,3,2])
        self.assertEqual(c['chosen_candidate_index'],1)
        self.assertEqual(c['candidates'][1]['snapshot']['image_size'],4)
        self.assertEqual(c['candidates'][1]['snapshot']['linear_rank'],3)

    def test_truthful_off_equilibrium_ambiguity(self):
        c=self.cert
        self.assertEqual(c['consensus_status'],'INTERPRETATION_AMBIGUOUS')
        witness=c['disagreement_witness']
        self.assertNotEqual(witness['first'],witness['second'])
        state=witness['initial'];cs=[x['future_anf'] for x in c['candidates']]
        self.assertEqual(witness['first'],[_eval(tuple(p),state) for p in cs[0]])
        self.assertEqual(witness['second'],[_eval(tuple(p),state) for p in cs[1]])

    def test_all_candidates_agree_on_original_fixed_points(self):
        _,_,clauses=source_reduce(self.src)
        for x in range(128):
            if all(any(((x>>(abs(l)-1))&1)==int(l>0) for l in row) for row in clauses):
                expected=[(x>>t)&1 for t in self.cert['intent']['targets']]
                for candidate in self.cert['candidates']:
                    self.assertEqual([_eval(tuple(p),x) for p in candidate['future_anf']],expected)

    def test_zero_time_consensus_is_mathematically_exact(self):
        c,_=compile_language(self.src,self.cut,steps=0)
        self.assertEqual(c['consensus_status'],'CONSENSUS_IN_DISCOVERED_CLASS')
        self.assertTrue(verify(self.src,c,intention=c['intent']))
        self.assertEqual(len({str(candidate['future_anf']) for candidate in c['candidates']}),1)

    def test_first_step_ambiguity_and_time_leap(self):
        for t in (1,2,3,5,10**100+173):
            with self.subTest(time=t):
                c,_=compile_language(self.src,self.cut,steps=t)
                self.assertTrue(verify(self.src,c,intention=c['intent']))
                self.assertEqual(c['consensus_status'],'INTERPRETATION_AMBIGUOUS')

    def test_orientation_search_must_be_complete_to_claim_consensus(self):
        with self.assertRaises(GroundRefusal):
            compile_language(self.src,self.cut,max_candidates=1)

    def test_undisclosed_source_change_rejected(self):
        tampered=copy.deepcopy(self.src)
        tampered['coupling'][-1][0] *= -1
        with self.assertRaises(Reject):verify(tampered,self.cert,intention=self.cert['intent'])

    def test_source_receipt_fields_are_not_self_certifying(self):
        changes=[
          lambda c:c['candidates'][0]['future_anf'][0].append(123),
          lambda c:c['candidates'][0]['feature_matrix_rows'].__setitem__(0,0),
          lambda c:c['candidates'][1]['snapshot'].__setitem__('minimum_binary_bits',1),
          lambda c:c['candidates'][1]['snapshot']['encoder_anf'][0].append(77),
          lambda c:c['candidates'][1]['snapshot']['decoder'].reverse(),
          lambda c:c['candidates'][0].__setitem__('status','BUDGET_REFUSAL'),
          lambda c:c['candidate_class'].__setitem__('conflict_free_count',3),
          lambda c:c.__setitem__('chosen_candidate_index',3),
          lambda c:c.__setitem__('consensus_status','CONSENSUS_IN_DISCOVERED_CLASS'),
          lambda c:c['disagreement_witness'].__setitem__('initial',0),
          lambda c:c['ledger'].__setitem__('candidate_matrix_products',1),
          lambda c:c['intent'].__setitem__('steps','5'),
        ]
        for change in changes:
            with self.subTest(change=str(change)):
                c=copy.deepcopy(self.cert);change(c)
                with self.assertRaises(Reject):verify(self.src,c,intention=self.cert['intent'])

    def test_incomplete_feature_budget_refuses_universal_claim(self):
        c,_=compile_language(self.src,self.cut,max_features=8)
        self.assertEqual(c['consensus_status'],'UNKNOWN_INCOMPLETE_CANDIDATE_PROOFS')
        self.assertTrue(verify(self.src,c,intention=c['intent']))

    def test_nonfunctional_cnf_is_rejected(self):
        tampered=copy.deepcopy(self.src);tampered['coupling']=tampered['coupling'][:1]
        with self.assertRaises(GroundRefusal):compile_language(tampered,self.cut)

    def test_deterministic_source_certificate_independent_of_wall_clock(self):
        a,_=compile_language(self.src,self.cut)
        self.assertEqual(a,self.cert)

if __name__=='__main__':unittest.main()
