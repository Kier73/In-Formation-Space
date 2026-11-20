import copy
import unittest
from cocycle import ExactSchedule
from moving_frame import first_native_cubic_echo
from receipt import make_receipt, verify_receipt

class ReceiptTests(unittest.TestCase):
    def test_echo_search_and_not_found_scope(self):
        s=ExactSchedule(31,(0,))
        self.assertEqual(first_native_cubic_echo(s,7,max_steps=1)['status'],'not_found_within_budget')
        answer=first_native_cubic_echo(s,7,max_steps=10)
        self.assertEqual(answer['coordinate'],2)
        self.assertEqual(answer['countergate_cubic'],7)
        self.assertEqual(answer['search_operations'],2)
        with self.assertRaises(ValueError):
            first_native_cubic_echo(s,7,max_steps=0)

    def test_short_receipt_and_tamper_rejection(self):
        program={'p':31,'source':3,'events':[
            {'kind':'cubic','coefficient':7},
            {'kind':'schedule','pattern':[0],'steps_decimal':'2'},
            {'kind':'cubic','coefficient':7}],
            'coordinates':[3,28,1],'max_work':5}
        r=make_receipt(program)
        self.assertTrue(verify_receipt(r))
        self.assertEqual(r['admission']['status'],'admitted')
        self.assertEqual(r['state']['blocks'],[])
        self.assertLess(r['independent_short_dense_max_error'],1e-12)
        altered=copy.deepcopy(r)
        altered['program']['source']=4
        self.assertFalse(verify_receipt(altered))
        altered=copy.deepcopy(r)
        altered['predictions'][0][0]='0x1.0p+0'
        self.assertFalse(verify_receipt(altered))
        altered=copy.deepcopy(r)
        altered['state']['blocks']=[{'axis':[0,1],'cubic_mod_p':1,'harmonics':[]}]
        self.assertFalse(verify_receipt(altered))

    def test_long_and_refused_receipts(self):
        program={'p':17,'source':3,'events':[
            {'kind':'cubic','coefficient':5},
            {'kind':'schedule','pattern':[0],'steps_decimal':str(10**100+2)},
            {'kind':'cubic','coefficient':5}],
            'coordinates':[14],'max_work':1}
        r=make_receipt(program)
        self.assertTrue(verify_receipt(r))
        self.assertEqual(r['state']['blocks'],[])
        self.assertIsNone(r['independent_short_dense_max_error'])
        refused={'p':17,'source':3,'events':[
            {'kind':'cubic','coefficient':5},
            {'kind':'schedule','pattern':[0],'steps_decimal':'1'},
            {'kind':'cubic','coefficient':5}],
            'coordinates':[5],'max_work':5}
        result=make_receipt(refused)
        self.assertEqual(result['admission']['status'],'refused_cost')
        self.assertEqual(result['predictions'],[])
        self.assertTrue(verify_receipt(result))

    def test_receipt_adversarial_parsing(self):
        base={'p':17,'source':1,'events':[{'kind':'schedule','pattern':[1],'steps_decimal':'01'}],
              'coordinates':[1],'max_work':100}
        with self.assertRaises(ValueError):make_receipt(base)
        base['events'][0]['steps_decimal']='1'
        base['events'][0]['unknown']=1
        with self.assertRaises(ValueError):make_receipt(base)
        base['events']=[{'kind':'harmonic','strength_hex':'nan'}]
        with self.assertRaises(ValueError):make_receipt(base)
        base['events']=[{'kind':'harmonic','strength_hex':'0x1.999999999999ap-4'}]
        self.assertTrue(verify_receipt(make_receipt(base)))

if __name__=='__main__':unittest.main()
