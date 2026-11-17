"""Source-grounded RCG-005 adversarial and independent oracle tests."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import random
import unittest

from connectome_ground import ConnectomeGround
from temporal_ground import SparseTransfer, TemporalGroundRefused, hash_object
from conjugate_ground import (
    ConjugatedGround, prepare_shared, verify_shared, navigate, verify_result,
    quotient_power,
)
from test_temporal_ground import fixture, make_sparse_fixture


def ground_from(source, names):
    op=SparseTransfer.from_ground(source,names[0],names[0])
    return ConjugatedGround(op,tuple(names))


def independent_dense_vector(op: SparseTransfer,tick:int)->list[int]:
    """Power an explicit independent dense matrix (tiny fixture only)."""
    n,p=op.n,op.field
    matrix=[[0]*n for _ in range(n)]
    for src,outputs in enumerate(op.column_edges):
        for dst,w in outputs:
            matrix[dst][src]=(matrix[dst][src]+w)%p
    state=[0]*n
    state[op.names.index(op.source)]=1
    def mm(a,b):
        product=[[0]*n for _ in range(n)]
        for i in range(n):
            for k,x in enumerate(a[i]):
                if x:
                    for j,y in enumerate(b[k]):
                        if y:product[i][j]=(product[i][j]+x*y)%p
        return product
    def mv(a,v):
        return [sum(aij*vj for aij,vj in zip(row,v))%p for row in a]
    while tick:
        if tick&1:state=mv(matrix,state)
        tick>>=1
        if tick:matrix=mm(matrix,matrix)
    return state


class NonlinearSharedOrbitTests(unittest.TestCase):
    def setUp(self):
        self.source=fixture()
        self.names=('AWCL','ASER','ASIL','AIYL')
        self.model=ground_from(self.source,self.names)
        self.cert=prepare_shared(self.model)

    def test_nonlin_map_is_genuine_and_polynomial_inverse_over_full_field(self):
        model=self.model;op=model.operator
        randomizer=random.Random(1337)
        for _ in range(10):
            x=[randomizer.randrange(op.field) for _ in range(op.n)]
            self.assertEqual(model.decode(model.encode(x)),x)
            self.assertEqual(model.encode(model.decode(x)),x)
        x=model.initial();y=[0]*op.n;y[model.positions[1]]=1
        summed=[(a+b)%op.field for a,b in zip(x,y)]
        actual=model.step(summed)
        separate=model.step(x),model.step(y)
        linear=[(a+b)%op.field for a,b in zip(*separate)]
        self.assertNotEqual(actual,linear,'the generated F(x) must not simply be linear')
        self.assertEqual(model.description['transition'],
                         'decode(linear_sparse_step(encode(state)))')

    def test_small_and_huge_times_match_independent_dense_power(self):
        cert=self.cert;model=self.model
        verify_shared(model,cert)
        for tick in [0,1,2,3,4,5,8,15,100,2**56+73,2**63-1]:
            observed=navigate(model,cert,tick,trusted_certificate=True)
            y=independent_dense_vector(model.operator,tick)
            reconstructed=model.decode(y)[model.positions[0]]
            self.assertEqual(observed['nonlinear_readout'],reconstructed)
            self.assertEqual(observed['latent_readouts'],
                             {name:y[i] for name,i in zip(model.coordinates,model.positions)})
            if tick <= 8:
                self.assertEqual(observed['nonlinear_readout'],model.direct_at(tick))
                verify_result(model,cert,observed)
        self.assertLess(navigate(model,cert,2**56+73,trusted_certificate=True)['polynomial_products'],140)

    def test_global_vector_annihilator_replaces_individual_readout_proofs(self):
        op=self.model.operator
        degree=self.cert['recurrence_degree'];cc=self.cert['coefficients'];p=op.field
        self.assertGreater(degree,0)
        current=self.model.initial();vectors=[]
        for _ in range(degree+1):
            vectors.append(current);current=op.step(current)
        for col in range(op.n):
            self.assertEqual((vectors[degree][col]-sum(
                cc[i]*vectors[degree-1-i][col] for i in range(degree)))%p,0)
        self.assertEqual(len(self.cert['initial_terms']),len(self.names))
        self.assertEqual(self.cert['training_terms'],2*op.n)

    def test_changed_ground_and_rehashed_fake_certificates_rejected(self):
        cert=self.cert
        for edit in ('coefficient','readout','alpha','dimension','version','digest'):
            altered=copy.deepcopy(cert)
            if edit=='coefficient':altered['coefficients'][0]=(altered['coefficients'][0]+1)%self.model.operator.field
            if edit=='readout':altered['initial_terms'][self.names[1]][0]=(altered['initial_terms'][self.names[1]][0]+1)%self.model.operator.field
            if edit=='alpha':altered['model']['alphas'][0]+=1
            if edit=='dimension':altered['recurrence_degree']-=1
            if edit=='version':altered['model']['schema']='unadmitted-model'
            if edit!='digest':altered['digest']=hash_object({k:v for k,v in altered.items() if k!='digest'})
            else:altered['digest']='0'*64
            with self.subTest(edit=edit),self.assertRaises(TemporalGroundRefused):
                verify_shared(self.model,altered)
        changed=ConnectomeGround.from_csv(self.source_to_bytes().replace(b'AWCL,AWCR,11',b'AWCL,AWCR,12'),require_original=False)
        replaced=ground_from(changed,self.names)
        with self.assertRaises(TemporalGroundRefused):
            verify_shared(replaced,cert)
        other=ConjugatedGround(self.model.operator,self.names,seed='alternate-ground')
        with self.assertRaises(TemporalGroundRefused):
            verify_shared(other,cert)

    def source_to_bytes(self):
        from test_temporal_ground import FIXTURE
        return FIXTURE.encode()

    def test_navigation_rejects_forged_result_even_when_rehashed(self):
        original=navigate(self.model,self.cert,2**56+73)
        altered=copy.deepcopy(original)
        altered['nonlinear_readout']=(altered['nonlinear_readout']+1)%self.model.operator.field
        altered['digest']=hash_object({k:v for k,v in altered.items() if k!='digest'})
        with self.assertRaisesRegex(TemporalGroundRefused,'nonlinear result'):
            verify_result(self.model,self.cert,altered)
        with self.assertRaises(TemporalGroundRefused):
            navigate(self.model,self.cert,True)
        with self.assertRaises(TemporalGroundRefused):
            navigate(self.model,self.cert,2**63)
        with self.assertRaises(TemporalGroundRefused):
            ConjugatedGround(self.model.operator,('AWCL','AWCL'))

    def test_scaled_448_graph_and_four_reusable_latent_readouts(self):
        g=make_sparse_fixture(448,8,137)
        ground=ground_from(g,('V0001','V0111','V0222','V0333'))
        cert=prepare_shared(ground)
        verify_shared(ground,cert)
        self.assertGreaterEqual(cert['recurrence_degree'],300)
        for tick in (0,1,2,3,5,8,17,2**56+73):
            result=navigate(ground,cert,tick,trusted_certificate=True)
            if tick<=17:
                self.assertEqual(result['nonlinear_readout'],ground.direct_at(tick))
            else:
                self.assertLessEqual(result['polynomial_products'],2*tick.bit_length())
        self.assertEqual(result['requested_coordinate_count'],4)

    def test_real_openworm_source_when_available(self):
        path=Path(__file__).resolve().parents[2]/'data'/'herm_full_edgelist.csv'
        if not path.exists():
            self.skipTest('the source-pinned CSV is stored in the parent GitHub branch')
        original=ConnectomeGround.from_csv(path.read_bytes())
        graph=ground_from(original,('ASHL','AVAL','AVBL','AVAR'))
        cert=prepare_shared(graph)
        verify_shared(graph,cert)
        for tick in (0,1,3,11,2**56+73):
            result=navigate(graph,cert,tick,trusted_certificate=True)
            if tick<=11:self.assertEqual(result['nonlinear_readout'],graph.direct_at(tick))
        self.assertEqual(graph.operator.n,448)


if __name__=='__main__':
    unittest.main()
