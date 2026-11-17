"""RCG-006: full-state proof checks, synthetic learning, and independent oracles."""
from __future__ import annotations
import copy
from pathlib import Path
import unittest
from connectome_ground import ConnectomeGround
from temporal_ground import MODULUS,hash_object
from conjugate_ground import ConjugatedGround
from observer_quotient import (
    ExpandedSyntheticGround, DirectSourceOperator, QuotientRefused, _pack_partition, _unpack_partition,
    discover, verify, quotient_operator, quotient_at, verify_query,
    micro_observation, _equitable,
)

ORIGINAL = Path(__file__).resolve().parents[2] / 'data' / 'herm_full_edgelist.csv'
FIXTURE = '''Source,Target,Weight,Type
AWCL,ASER,1,chemical
AWCL,AWCR,11,chemical
AWCL,AIYL,22,chemical
AWCL,AIBL,12,chemical
ASER,AIYL,9,chemical
ASER,AIBR,32,chemical
ASIL,AIYL,3,chemical
ASIL,AWCL,3,chemical
AWCR,AIYL,12,chemical
AFDL,AIYL,25,chemical
'''


def source():
    return ConnectomeGround.from_csv(FIXTURE.encode(),require_original=False)


class IndependentChangedEdge:
    """Receiver sees a changed connection despite a possibly rehashed claim."""
    def __init__(self, original):
        self.original=original
        self.n=original.n
        self.field=original.field
        self.fingerprint=original.fingerprint
        self.description=original.description
        self.source_blob=original.source_blob
        self.source_fingerprint=original.source_fingerprint
        self.copies=original.copies
        self.groups=original.groups

    def outgoing(self,src):
        edges=list(self.original.outgoing(src))
        if src==0:
            # Conservation of total mass, but moves it into a *different* macro class.
            target=self.original.visible(0)
            edges[0]=(target,edges[0][1])
        return tuple(edges)

    def output_mask(self):
        return self.original.output_mask()

    def transpose_step(self,row):
        return [sum(w*row[d] for d,w in self.outgoing(i))%self.field for i in range(self.n)]


class ObserverQuotientTests(unittest.TestCase):
    def setUp(self):
        self.ground=ExpandedSyntheticGround(source(),groups=8,copies=32,seed=11)

    def test_nontrivial_learned_partition_all_sources_and_future(self):
        op=self.ground
        cert=discover(op,horizon=20)
        part,q=verify(op,cert,replay_observations=True)
        self.assertEqual(cert['class_count'],8)
        self.assertGreater(cert['training_horizon'],0)
        self.assertLess(cert['training_horizon'],op.n)
        self.assertEqual(len(part),op.n)
        self.assertLess(len(cert['partition_deflate_b64']),op.n)
        # The proposer receives output observations only, not the generator's g labels.
        for micro in [0,1,2,3,19,54,91,144,op.n-1]:
            Q,g=quotient_operator(op,cert,micro,trusted=(part,q))
            self.assertEqual(Q.n,8)
            for tick in [0,1,2,3,6,9,17]:
                full=micro_observation(op,part,micro,tick)
                state=[0]*Q.n
                state[g]=1
                for _ in range(tick):
                    state=Q.step(state)
                self.assertEqual(state,full,
                    f'P M^{tick} e_micro should equal Q^{tick} P e_micro')
            result=quotient_at(op,cert,micro,2**56+73,depth=6,trusted=(part,q))
            verify_query(op,cert,result,trusted=(part,q))
            self.assertEqual(result['microstate_vectors_realized_for_query'],0)
            self.assertEqual(result['neural_result']['requested_coordinate_count'],7)

    def test_nonlinear_decoder_matches_full_micro_oracle(self):
        op=self.ground
        cert=discover(op)
        part,q=verify(op,cert)
        for micro in [0,7,19,128,255]:
            Q,g=quotient_operator(op,cert,micro,trusted=(part,q))
            names=tuple(Q.names[(g+i)%Q.n] for i in range(7))
            chart=ConjugatedGround(Q,names,seed='rcg006-observer-quotient-neural-v1')
            for tick in (0,1,2,3,7,12):
                full=micro_observation(op,part,micro,tick)
                want=chart.readout_decode({name:full[Q.names.index(name)] for name in names})
                # Direct nonlinear F^t reference uses the actual 8-state quotient.
                self.assertEqual(chart.direct_at(tick),want)
                report=quotient_at(op,cert,micro,tick,depth=6,trusted=(part,q))
                self.assertEqual(report['neural_result']['nonlinear_readout'],want)

    def test_mixture_of_arbitrary_initial_states_exact_quotient(self):
        op=self.ground
        cert=discover(op)
        part,q=verify(op,cert)
        init=[(i*i+17*i+19) % op.field for i in range(op.n)]
        macro=[0]*len(q)
        for i,v in enumerate(init):
            macro[part[i]]=(macro[part[i]]+v)%op.field
        target=macro[:]
        # This verifies all-state exactness, not only the source-unit impulse used
        # by RCG-004/005.
        Q,_=quotient_operator(op,cert,0,trusted=(part,q))
        micro=init
        for _ in range(8):
            micro=op.step(micro)
            target=Q.step(target)
            observed=[0]*len(q)
            for i,v in enumerate(micro):
                observed[part[i]]=(observed[part[i]]+v)%op.field
            self.assertEqual(target,observed)

    def test_forged_candidate_partition_rehashed_refused(self):
        op=self.ground
        cert=discover(op)
        part,q=verify(op,cert)
        bad=copy.deepcopy(cert)
        part[0]=(part[0]+1)%bad['class_count']
        bad['partition_deflate_b64']=_pack_partition(part)
        bad['digest']=hash_object({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(QuotientRefused,'intertwining|learner'):
            verify(op,bad,replay_observations=True)

    def test_changed_one_micro_connection_breaks_source_law(self):
        op=self.ground
        cert=discover(op)
        fake=IndependentChangedEdge(op)
        with self.assertRaisesRegex(QuotientRefused,'intertwining'):
            _equitable(fake, _unpack_partition(cert['partition_deflate_b64'],op.n),
                       cert['class_count'],op.output_mask())

    def test_rehashed_forged_quotient_and_training_trace_refused(self):
        op=self.ground
        cert=discover(op)
        bad=copy.deepcopy(cert)
        bad['quotient_columns'][0][0][1]=(bad['quotient_columns'][0][0][1]+1)%MODULUS
        bad['digest']=hash_object({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(QuotientRefused,'coefficients'):
            verify(op,bad,replay_observations=False)
        bad=copy.deepcopy(cert)
        bad['observation_row_digests'][-1]='0'*64
        bad['digest']=hash_object({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(QuotientRefused,'observed training'):
            verify(op,bad,replay_observations=True)

    def test_changed_source_and_neural_reply_rejected(self):
        op=self.ground
        cert=discover(op)
        other=ExpandedSyntheticGround(source(),groups=8,copies=32,seed=12)
        with self.assertRaisesRegex(QuotientRefused,'source'):
            verify(other,cert)
        report=quotient_at(op,cert,0,2**56+73,depth=6)
        report['neural_result']['nonlinear_readout']+=1
        report['digest']=hash_object({k:v for k,v in report.items() if k!='digest'})
        with self.assertRaisesRegex(QuotientRefused,'observation disagrees'):
            verify_query(op,cert,report)

    def test_direct_unaltered_source_is_not_assumed_to_compress(self):
        original=source()
        # This is a real source-row fixture, NOT the procedurally expanded
        # network: some output channels quotient, others do not.
        direct=DirectSourceOperator(original,target='AIYL')
        certificate=discover(direct,horizon=24)
        partition,q=verify(direct,certificate,replay_observations=True)
        self.assertEqual(direct.n,8)
        self.assertEqual(certificate['class_count'],6)
        for micro in (0,1,direct.n-1):
            Q,g=quotient_operator(direct,certificate,micro,trusted=(partition,q))
            for tick in (0,1,2,4,7,12):
                target=micro_observation(direct,partition,micro,tick)
                x=[0]*Q.n;x[g]=1
                for _ in range(tick):x=Q.step(x)
                self.assertEqual(x,target)
        # No valid small partition for the alternative channel under 24
        # observed horizons: a counterexample to guaranteed compression.
        no_shortcut=DirectSourceOperator(original,target='AWCL')
        with self.assertRaisesRegex(QuotientRefused,'no globally verified'):
            discover(no_shortcut,horizon=24)

    def test_original_source_pinned_heterogeneous_generator_when_available(self):
        if not ORIGINAL.exists():
            self.skipTest('original source is in stacked GitHub branch; local fixture only')
        source_ground=ConnectomeGround.from_csv(ORIGINAL.read_bytes(),require_original=True)
        op=ExpandedSyntheticGround(source_ground,groups=16,copies=64,seed=23)
        cert=discover(op)
        p,q=verify(op,cert)
        self.assertEqual(cert['class_count'],16)
        self.assertEqual(cert['expanded']['source_blob'],source_ground.source_blob)
        observation=quotient_at(op,cert,77,2**56+73,depth=6,trusted=(p,q))
        verify_query(op,cert,observation,trusted=(p,q))


if __name__=='__main__':
    unittest.main()
