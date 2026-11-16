"""RCG-004: mathematical source, scale, refusal and independent oracle tests."""
from __future__ import annotations

from pathlib import Path
import random
import unittest

from connectome_ground import ConnectomeGround
from temporal_ground import (
    MODULUS, TemporalGroundRefused, SparseTransfer, hash_object,
    prepare, verify_preparation, navigate_verified, validate_navigation,
)

FIXTURE = """Source,Target,Weight,Type
AWCL,ASER,1,chemical
AWCL,ASGR,1,chemical
AWCL,ASIL,1,chemical
AWCL,AWCR,11,chemical
AWCL,AFDL,2,chemical
AWCL,AIAL,2,chemical
AWCL,AIAR,4,chemical
AWCL,AIBL,12,chemical
AWCL,AIBR,2,chemical
AWCL,AIYL,22,chemical
AWCL,AIZL,1,chemical
AWCL,RIAL,6,chemical
AWCL,AVAL,1,chemical
AWCL,SMDVL,1,chemical
ASER,AIYL,9,chemical
ASER,AIBR,32,chemical
ASIL,AIYL,3,chemical
ASIL,AWCL,3,chemical
AWCR,AIYL,12,chemical
AFDL,AIYL,25,chemical
"""


def fixture():
    return ConnectomeGround.from_csv(FIXTURE.encode(), require_original=False)


def make_sparse_fixture(size: int, fanout: int, seed: int) -> ConnectomeGround:
    """Synthetic random topology: not a biological connectome."""
    rng = random.Random(seed)
    edges = set()
    for i in range(size):
        for _ in range(fanout):
            j = (i+1+rng.randrange(size-1)) % size
            edges.add((i,j))
    csv = "Source,Target,Weight,Type\n" + "\n".join(
        f"V{i:04d},V{j:04d},{1+(i*11+j*7)%31},chemical"
        for i,j in sorted(edges)) + "\n"
    return ConnectomeGround.from_csv(csv.encode(), require_original=False)


def independent_dense_power(op: SparseTransfer, tick: int) -> int:
    """Separate full dense matrix powering, not recurrence arithmetic."""
    n,p = op.n,op.field
    matrix = [[0]*n for _ in range(n)]
    for i,outputs in enumerate(op.column_edges):
        for j,w in outputs:
            matrix[j][i] = (matrix[j][i]+w)%p
    x=[0]*n
    x[op.names.index(op.source)] = 1

    def mm(left,right):
        result=[[0]*n for _ in range(n)]
        for i in range(n):
            for k,a in enumerate(left[i]):
                if a:
                    for j,b in enumerate(right[k]):
                        if b:
                            result[i][j]=(result[i][j]+a*b)%p
        return result

    def mv(m,vec):
        return [sum(a*b for a,b in zip(row,vec))%p for row in m]

    while tick:
        if tick & 1:
            x=mv(matrix,x)
        tick >>= 1
        if tick:
            matrix=mm(matrix,matrix)
    return x[op.names.index(op.target)]


class TemporalGroundTests(unittest.TestCase):
    def test_far_future_exact_independent_dense_power(self):
        g=fixture()
        for src,target in [('AWCL','AIYL'),('AWCL','AIBR'),
                           ('ASER','AIYL'),('ASGR','AWCL')]:
            op=SparseTransfer.from_ground(g,src,target)
            cert=prepare(op)
            verify_preparation(op,cert)
            for t in (0,1,2,3,5,31,100,2**56+73,2**63-1):
                report=navigate_verified(cert,t)
                self.assertEqual(report['value_mod_p'],
                                 independent_dense_power(op,t))
                validate_navigation(op,cert,report,verify_source=False)
            self.assertLessEqual(cert['recurrence_degree'],len(g.nodes))

    def test_proof_rejects_rehashed_forged_coefficients(self):
        op=SparseTransfer.from_ground(fixture(),'AWCL','AIYL')
        cert=prepare(op)
        altered=dict(cert)
        altered['coefficients']=list(altered['coefficients'])
        altered['coefficients'][0]=(altered['coefficients'][0]+1)%MODULUS
        altered['digest']=hash_object({k:v for k,v in altered.items() if k!='digest'})
        with self.assertRaisesRegex(TemporalGroundRefused,'recurrence'):
            verify_preparation(op,altered)

    def test_original_connectome_is_receiver_owned(self):
        g=fixture()
        cert=prepare(SparseTransfer.from_ground(g,'AWCL','AIYL'))
        changed=ConnectomeGround.from_csv(
            FIXTURE.replace('AWCL,AWCR,11,chemical',
                            'AWCL,AWCR,12,chemical').encode(),
            require_original=False)
        op=SparseTransfer.from_ground(changed,'AWCL','AIYL')
        with self.assertRaises(TemporalGroundRefused):
            verify_preparation(op,cert)
        with self.assertRaises(TemporalGroundRefused):
            SparseTransfer.from_ground(g,'AWCL','UNLISTED')
        with self.assertRaises(TemporalGroundRefused):
            SparseTransfer.from_ground(g,'AWCL','AIYL',modulus=65521)

    def test_zero_recurrence_and_invalid_timing(self):
        op=SparseTransfer.from_ground(fixture(),'ASGR','AWCL')
        cert=prepare(op)
        self.assertEqual(cert['recurrence_degree'],0)
        for t in (0,1,17,2**60):
            self.assertEqual(navigate_verified(cert,t)['value_mod_p'],0)
        with self.assertRaises(TemporalGroundRefused):
            navigate_verified(cert,-1)
        with self.assertRaises(TemporalGroundRefused):
            navigate_verified(cert,2**63)
        with self.assertRaises(TemporalGroundRefused):
            navigate_verified(cert,True)

    def test_448_node_scaled_synthetic_operator(self):
        g=make_sparse_fixture(448,8,137)
        op=SparseTransfer.from_ground(g,'V0001','V0222')
        cert=prepare(op)
        verify_preparation(op,cert)
        self.assertEqual(op.n,448)
        self.assertTrue(300 <= cert['recurrence_degree'] <= 448)
        for t in (0,3,8,31,447,575):
            self.assertEqual(navigate_verified(cert,t)['value_mod_p'],
                             op.samples(t+1)[-1])
        far=navigate_verified(cert,2**56+73)
        self.assertLess(far['polynomial_products'],150)
        self.assertEqual(far['value_mod_p'],665424168)

    def test_real_pinned_original_connectome_in_ci(self):
        path=Path(__file__).resolve().parents[1]/'data'/'herm_full_edgelist.csv'
        if not path.is_file():
            self.skipTest('pinned OpenWorm file is only in repository, not fixture runtime')
        g=ConnectomeGround.from_csv(path.read_bytes())
        self.assertEqual(len(g.nodes),448)
        op=SparseTransfer.from_ground(g,'ASHL','AVAL')
        cert=prepare(op)
        verify_preparation(op,cert)
        for t in (0,1,2,3,25,448,2**56+73):
            validate_navigation(op,cert,navigate_verified(cert,t),
                                verify_source=False)
        self.assertGreater(cert['recurrence_degree'],0)

    def test_native_ecpu_recurrence_agreement_when_available(self):
        try:
            from mailcpu.law_certifier import berlekamp_massey
        except ImportError:
            self.skipTest('native E-CPU required by hosted native job')
        op=SparseTransfer.from_ground(fixture(),'AWCL','AIYL')
        self.assertEqual(prepare(op,native_ecpu=True),prepare(op))


if __name__=="__main__":
    unittest.main()
