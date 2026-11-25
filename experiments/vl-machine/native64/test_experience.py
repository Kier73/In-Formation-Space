import copy, unittest
from experience import campaign, replay, train_tools, evaluate, task, observe, digest, shape, wire, construct
from template_ground import Template

class Experience(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.ledger,cls.report=campaign()
    def test_curriculum(self):
        r=self.report;self.assertEqual(r['training_counts'],{'arithmetic':12,'navigate':12,'compose':12,'invalid':4});self.assertEqual(r['shapes'],4);self.assertEqual(r['evaluation']['verified'],128);self.assertEqual(r['evaluation']['rejections'],4);self.assertEqual(r['evaluation']['constructor'],128)
        self.assertEqual(r['status']['expected_rejection'],12);self.assertEqual(len(r['catalogue']),3);self.assertEqual(len(r['challenge_misses']),8);self.assertEqual(r['initial_evaluation']['constructor'],96);self.assertEqual(r['initial_evaluation']['ordinary'],36)
    def test_replay_and_tampering(self):
        l=self.ledger;self.assertEqual(replay(l.rows,l.head).head,l.head)
        bad=copy.deepcopy(l.rows);bad[0]['experience']['output'][0]^=1;bad[0]['digest']=digest({k:v for k,v in bad[0].items() if k!='digest'})
        with self.assertRaises(ValueError):replay(bad,l.head)
        with self.assertRaises(ValueError):replay(l.rows[:-1],l.head)
    def test_final_not_training(self):
        rows=self.ledger.rows;cat,dec=train_tools(rows,refined=True);cat2,dec2=train_tools([r for r in rows if r['experience']['task']['phase']!='final'],refined=True);self.assertEqual(dec,dec2);self.assertEqual(cat,cat2)
        decoded={k:Template.decode(bytes.fromhex(v)) for k,v in self.report['catalogue'].items()};counts,results=evaluate(rows,decoded);self.assertEqual(digest(results),self.report['final_results_digest'])
    def test_shape_sensor(self):
        self.assertEqual(shape(wire(construct(task('navigate','train',1)))),shape(wire(construct(task('navigate','final',3)))))
        self.assertNotEqual(shape(wire(construct(task('navigate','train',1)))),shape(wire(construct(task('compose','train',1)))));self.assertEqual(shape(wire(construct(task('compose','train',1)))),shape(wire(construct(task('fork','challenge',1)))))
        self.assertEqual(observe(task('invalid','final',0))['status'],'expected_rejection')
if __name__=='__main__':unittest.main()
