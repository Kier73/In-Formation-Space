import json
import os
import sys
import unittest
from dataclasses import replace
from itertools import product
from pathlib import Path

from clt import (fixture, transport, check_chart, derived_parity, witness_plan,
                 power_navigation, raw_cycle, form_observer_machine, verify_formed_machine)


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = [fixture(8, 17), fixture(5, 41, neural=True), fixture(3, 93)]
        cls.fine = [form_observer_machine(s, ("zero",)) for s, _ in cls.sources]
        cls.old = [form_observer_machine(s, ("parity",)) for s, _ in cls.sources]

    def test_heterogeneous_transport_and_composition(self):
        a, b, c = self.fine
        self.assertEqual([len(s.states) for s, _ in self.sources], [64,40,24])
        self.assertEqual([len(m.groups) for m in self.fine], [8,8,8])
        self.assertEqual([len(m.groups) for m in self.old], [2,2,2])
        ab, bc, ac = transport(a,b), transport(b,c), transport(a,c)
        self.assertEqual(tuple(bc[i] for i in ab), ac)
        self.assertEqual(tuple(transport(b,a)[i] for i in ab), tuple(range(8)))
        for s,m in zip(self.sources,self.fine):
            self.assertTrue(verify_formed_machine(s[0],m))
        # Independent source-coordinate oracle, withheld from discovery.
        for i, (z, _) in enumerate(self.sources[0][1]):
            for j, (z2, _) in enumerate(self.sources[1][1]):
                self.assertEqual(ab[a.state_groups[i]] == b.state_groups[j], z == z2)

    def test_all_short_words_against_native_source(self):
        count = 0
        for (s,_), m in zip(self.sources,self.fine):
            for i in range(len(s.states)):
                for length in range(5):
                    for word in product(range(3), repeat=length):
                        native_word = [s.actions[j] for j in word]
                        result = m.apply({"initial_state":s.states[i], "word":native_word})
                        self.assertEqual(result["observation"],
                                         s.replay(s.states[i],native_word,m.fields))
                        count += 1
        self.assertEqual(count,15488)
        print("short_word_observations",count)

    def test_corruption_and_forgery(self):
        s,_ = fixture(5,41,corrupt=True)
        bad = form_observer_machine(s,("zero",))
        with self.assertRaises(ValueError):
            transport(self.fine[0],bad)
        chart = list(transport(self.fine[0],self.fine[1]))
        chart[0],chart[1] = chart[1],chart[0]
        with self.assertRaises(ValueError):
            check_chart(self.fine[0],self.fine[1],chart)
        # Same immediate parity output does not preserve a future marker.
        self.assertEqual(len(self.old[0].groups),2)
        with self.assertRaises(ValueError):
            transport(self.old[0],self.fine[0])

    def test_recursive_discovery_and_minimal_refinement(self):
        for (s,_),fine,old in zip(self.sources,self.fine,self.old):
            derived = derived_parity(fine)
            compact = form_observer_machine(derived,("parity",))
            chart = transport(compact,old)
            for i in range(len(s.states)):
                self.assertEqual(chart[compact.state_groups[fine.state_groups[i]]],
                                 old.state_groups[i])
            subset,decoder = witness_plan(s,old,fine)
            self.assertEqual(subset,("upper1","upper2"))
            for i,row in enumerate(s.observations):
                self.assertEqual(decoder[(old.state_groups[i],row[2],row[3])],
                                 fine.state_groups[i])
            # Each old class has four genuinely distinct fine states;
            # no one-bit witness can recover them.
            for group in old.groups:
                self.assertEqual(len({fine.state_groups[i] for i in group}),4)

    def test_navigation_and_accounting(self):
        counts = []
        for (s,_),m in zip(self.sources,self.fine):
            for i in range(len(s.states)):
                for word in ((0,), (1,0,2), (2,1,0,0), ()):
                    for n in (0,1,2,7,17,101,10**12+39):
                        z,w = power_navigation(m.transitions,m.state_groups[i],word,n)
                        raw = raw_cycle(s.transitions,i,word,n)
                        self.assertEqual(z,m.state_groups[raw])
                        ref,wr = power_navigation(s.transitions,i,word,n)
                        self.assertEqual(ref,raw)
                        if n > 100 and word:
                            self.assertLess(w,wr)
            n = 10**12+39
            _,w = power_navigation(m.transitions,0,(0,),n)
            _,wr = power_navigation(s.transitions,0,(0,),n)
            counts.append({"source_states":len(s.states),"quotient_states":len(m.groups),
                           "source_power_table_reads":wr,"ground_power_table_reads":w})
        print("navigation_accounting",json.dumps(counts))

    def test_fresh_permutations(self):
        for seed in range(20,40):
            s,coords = fixture(1+seed%8,seed)
            m = form_observer_machine(s,("zero",))
            chart = transport(self.fine[0],m)
            for i,(z,_) in enumerate(self.sources[0][1]):
                for j,(other,_) in enumerate(coords):
                    self.assertEqual(chart[self.fine[0].state_groups[i]] == m.state_groups[j],
                                     z == other)

    def test_native_admitted_path_and_rehome(self):
        # Use the actual pinned E-CPU fixture inventory, not a second scheduler.
        sys.path.insert(0,str(Path(os.environ["ECPU_ROOT"])/"tests"))
        from test_intention_formed_fabric import environment
        from mailcpu.intention_formed_fabric import realize_formed_intention
        from mailcpu.substrate_bootstrap import verify_bootstrap_report
        s,_ = self.sources[1]
        results=[]
        for include_a in (True,False):
            inv,policy,carriers=environment(include_a=include_a)
            result=realize_formed_intention(
                s,("parity",),s.states[0],("step","fold","square"),
                inv,policy,carriers,
                admitted_interpreters=("compact-a","compact-b","general"),
                admitted_observers=("witness",),ingress="origin",observer="witness",coordinate=5)
            self.assertTrue(verify_bootstrap_report(result.report,result.task,result.plan))
            self.assertIn("compact-a" if include_a else "compact-b",
                          [step.locus for step in result.plan.steps])
            results.append(result)
        self.assertEqual(results[0].machine.fingerprint,results[1].machine.fingerprint)
        self.assertEqual(results[0].report["output"],results[1].report["output"])
        self.assertNotEqual(results[0].plan.fingerprint,results[1].plan.fingerprint)


if __name__ == "__main__":
    unittest.main()
