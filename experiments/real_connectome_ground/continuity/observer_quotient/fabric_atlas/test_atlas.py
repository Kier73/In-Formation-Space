"""Ground-independent and adverse-control tests for RCG-007 universal observable atlas."""
import copy,unittest
from connectome_ground import ConnectomeGround
from observer_quotient import ExpandedSyntheticGround,discover,verify,QuotientRefused
from temporal_ground import MODULUS,hash_object
from atlas import prepare_atlas,verify_atlas,execute_batch,verify_batch,_readout

SOURCE='''Source,Target,Weight,Type
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

class AtlasTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src=ConnectomeGround.from_csv(SOURCE.encode(),require_original=False)
        cls.op=ExpandedSyntheticGround(cls.src,groups=8,copies=32,seed=11)
        cls.cert=discover(cls.op)
        cls.atlas=prepare_atlas(cls.op,cls.cert)
        cls.trusted=verify_atlas(cls.op,cls.cert,cls.atlas)

    def test_arbitrary_mixtures_and_nonlinear_outputs_against_full_micro_graph(self):
        part,cols=self.trusted
        p=self.op.field
        queries=[]
        for i in range(12):
            kind=[{'kind':'class','index':i%8},
                  {'kind':'linear','weights':[int(j==i%8 or j==(i+2)%8) for j in range(8)]},
                  {'kind':'sum_squares','indices':[0,2,4,6]},
                  {'kind':'shear_pair','left':i%8,'right':(i+1)%8,'gain':13}][i%4]
            terms=[[i*5%self.op.n,3],[i*9%self.op.n,2],[i*5%self.op.n,7]]
            queries.append({'sources':terms,'readout':kind,'tick':6})
        report=execute_batch(self.op,self.cert,self.atlas,queries,trusted=self.trusted)
        self.assertEqual(report['query_count'],12)
        self.assertEqual(report['intermediate_microstates_realized'],0)
        for item,result in zip(queries,report['values']):
            state=[0]*self.op.n
            for index,weight in item['sources']:state[index]=(state[index]+weight)%p
            for _ in range(item['tick']):state=self.op.step(state)
            macro=[0]*len(cols)
            for idx,v in enumerate(state):macro[part[idx]]=(macro[part[idx]]+v)%p
            self.assertEqual(result,_readout(macro,item['readout'],p))

    def test_distant_mixed_source_reusable_global_certificate(self):
        ticks=[0,1,2,7,2**40+19,2**56+73]
        for tick in ticks:
            batch=[{'tick':tick,'sources':[[i,1],[i+1,7]],
                    'readout':{'kind':'shear_pair','left':j,'right':(j+1)%8,'gain':j+1}}
                   for j,i in enumerate([0,3,8,19])]
            received=execute_batch(self.op,self.cert,self.atlas,batch,trusted=self.trusted)
            verify_batch(self.op,self.cert,self.atlas,batch,received,trusted=self.trusted)
            self.assertEqual(len(received['values']),4)
            self.assertLessEqual(received['polynomial_products'],120)

    def test_changed_source_rehashed_atlas_and_wrong_reply_refused(self):
        alternate=ExpandedSyntheticGround(self.src,groups=8,copies=32,seed=12)
        with self.assertRaises(QuotientRefused):verify_atlas(alternate,self.cert,self.atlas)
        bad=copy.deepcopy(self.atlas)
        bad['coefficients'][-1]=(bad['coefficients'][-1]+1)%MODULUS
        bad['digest']=hash_object({k:v for k,v in bad.items() if k!='digest'})
        with self.assertRaisesRegex(QuotientRefused,'annihilator'):
            verify_atlas(self.op,self.cert,bad)
        q=[{'tick':3,'sources':[[2,1]],'readout':{'kind':'class','index':0}}]
        receipt=execute_batch(self.op,self.cert,self.atlas,q,trusted=self.trusted)
        receipt['values'][0]=(receipt['values'][0]+1)%MODULUS
        receipt['digest']=hash_object({k:v for k,v in receipt.items() if k!='digest'})
        with self.assertRaisesRegex(QuotientRefused,'disagrees'):
            verify_batch(self.op,self.cert,self.atlas,q,receipt,trusted=self.trusted)

    def test_schema_and_resource_refusals(self):
        q={'tick':1,'sources':[[2,1]],'readout':{'kind':'class','index':0}}
        for req in ([q]*65,[{**q,'tick':True}],[{**q,'sources':[[0,1]]*65}],
                    [{**q,'readout':{'kind':'sum_squares','indices':[0,0]}}],
                    [q,{**q,'tick':2}],
                    [{**q,'readout':{'kind':'unknown'}}]):
            with self.subTest(req=req[:1]),self.assertRaises(QuotientRefused):
                execute_batch(self.op,self.cert,self.atlas,req,trusted=self.trusted)

if __name__=='__main__':unittest.main()