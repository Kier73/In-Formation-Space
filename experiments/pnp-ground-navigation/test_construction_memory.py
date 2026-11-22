"""SFI-004: exact source memory, independent proofs, cost, and recovery tests."""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import random
import subprocess
import sys
import tempfile
import unittest

from construction_memory import (ConstructionMemory, _identity, _rebase,
                                 verify_memory)
from morphic_sat import compile_ground, digest, execute, normalize
from morphic_verifier import independent_count, verify
from recursive_sat_compiler import audit_refinement
from test_recursive_sat_compiler import REPAIRABLE, reference_count


class ConstructionMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/'snapshot.json'
        self.store=ConstructionMemory(self.path)

    def test_meta_compiled_ground_survives_source_strengthening(self):
        root=self.store.bootstrap(REPAIRABLE,6)
        self.assertEqual(root['method'],'self-refinement')
        self.assertEqual(len(root['ground']['registers']),4)
        audit_refinement(REPAIRABLE,6,root['ground'],root['refinement_report'])
        refined=[*REPAIRABLE,(-1,2)]
        next_record=self.store.extend(refined,6)
        self.assertEqual(next_record['method'],'monotone-reuse')
        self.assertEqual(next_record['parent_record'],root['digest'])
        self.assertEqual(next_record['baseline_registers'],5)
        self.assertEqual(len(next_record['ground']['registers']),4)
        self.assertEqual(next_record['ground']['instructions'],root['ground']['instructions'])
        self.assertNotEqual(next_record['source_sha256'],root['source_sha256'])
        self.assertTrue(verify(next_record['ground'])['proven'])
        self.assertEqual(independent_count(next_record['ground'],max_free=6),
                         reference_count(refined,6))
        before=self.store.observe(root['digest'],coordinate_budget=64,partition_size=16)
        after=self.store.observe(next_record['digest'],coordinate_budget=64,partition_size=16)
        self.assertEqual(before['result']['models'],5)
        self.assertEqual(after['result']['models'],4)
        self.assertEqual(after['result']['checked'],16)
        self.assertEqual(verify_memory(self.store.read())['source_checked_observations'],2)

    def test_entirely_conflicting_extension_cannot_reuse_previous_answer(self):
        original=self.store.bootstrap(REPAIRABLE,6)
        impossible=[*REPAIRABLE,(1,),(-1,)]
        refined=self.store.extend(impossible,6)
        self.assertEqual(len(refined['ground']['registers']),4)
        self.assertEqual(refined['method'],'monotone-reuse')
        old=self.store.observe(original['digest'],coordinate_budget=64,partition_size=16)
        new=self.store.observe(refined['digest'],coordinate_budget=64,partition_size=16)
        self.assertEqual(old['result']['status'],'SAT')
        self.assertEqual(new['result']['status'],'UNSAT')
        self.assertEqual(new['result']['models'],0)
        self.assertEqual(new['result']['checked'],16)

    def test_weakening_is_fresh_compilation_not_unproven_cache_use(self):
        root=self.store.bootstrap(REPAIRABLE,6)
        weakened=REPAIRABLE[:-1]
        with self.assertRaises(ValueError):
            _rebase(root['ground'],[list(c) for c in normalize(weakened,6)])
        resulting=self.store.extend(weakened,6)
        self.assertEqual(resulting['method'],'fresh-baseline')
        self.assertIsNone(resulting['parent_record'])
        self.assertEqual(resulting['ground'],compile_ground(weakened,6)[0])

    def test_changed_dimensions_cannot_inherit_an_unrelated_machine(self):
        self.store.bootstrap(REPAIRABLE,6)
        r=self.store.extend([*REPAIRABLE,(7,8)],8)
        self.assertEqual(r['method'],'fresh-baseline')
        self.assertEqual(r['source_n'],8)

    def test_unknown_is_not_an_unsat_proof_from_old_machine(self):
        self.store.bootstrap(REPAIRABLE,17)
        r=self.store.extend([*REPAIRABLE,(-1,2)],17)
        self.assertEqual(r['method'],'monotone-reuse')
        self.assertEqual(r['baseline_registers'],16)
        self.assertEqual(len(r['ground']['registers']),15)
        unknown=self.store.observe(r['digest'],coordinate_budget=1024,partition_size=1024)
        self.assertEqual(unknown['result']['status'],'UNKNOWN')
        self.assertEqual(unknown['result']['checked'],0)
        exact=self.store.observe(r['digest'],coordinate_budget=32768,partition_size=1024)
        self.assertEqual(exact['result']['models'],4*(1<<11))
        self.assertEqual(exact['result']['checked'],32768)
        self.assertTrue(verify_memory(self.store.read()))

    def test_snapshots_survive_independent_process_reconstruction(self):
        root=self.store.bootstrap(REPAIRABLE,6)
        r=self.store.extend([*REPAIRABLE,(-1,2)],6)
        script=("from construction_memory import ConstructionMemory\n"
                f"m=ConstructionMemory({str(self.path)!r})\n"
                f"assert m.read()['records'][-1]['digest']=={r['digest']!r}\n"
                f"x=m.observe({r['digest']!r},coordinate_budget=64,partition_size=16)\n"
                "print(x['result']['models'])\n")
        proc=subprocess.run([sys.executable,'-c',script],cwd=Path(__file__).parent,
                            capture_output=True,text=True,timeout=45)
        self.assertEqual(proc.returncode,0,proc.stdout+proc.stderr)
        self.assertEqual(proc.stdout.strip(),'4')
        with self.assertRaises(ValueError):self.store.read()  # another writer advanced head
        recovered=ConstructionMemory(self.path)
        self.assertEqual(recovered.read()['observations'][-1]['result']['models'],4)
        self.assertNotEqual(root['digest'],r['digest'])

    def test_forged_gate_table_and_source_refused_even_after_rehash(self):
        root=self.store.bootstrap(REPAIRABLE,6)
        r=self.store.extend([*REPAIRABLE,(-1,2)],6)
        for attack in ('gate','source','parent','residual','baseline','chain'):
            image=deepcopy(self.store.read())
            record=image['records'][1]
            if attack=='gate':
                record['ground']['instructions'][0]['table'][0]^=1
                record['ground']['digest']=_identity(record['ground'])
            elif attack=='source':
                record['source_clauses'].append([3]);record['source_sha256']=digest({
                    'n':6,'clauses':record['source_clauses']})
            elif attack=='parent':
                record['parent_record']='e'*64
            elif attack=='residual':
                record['ground']['residual']=[]
                record['ground']['digest']=_identity(record['ground'])
            elif attack=='baseline':
                record['baseline_registers']=4
            else:
                record['previous']='f'*64
            record['digest']=_identity(record)
            image['digest']=_identity(image)
            with self.assertRaises(ValueError,msg=attack):verify_memory(image)
        self.assertEqual(root['ground']['digest'],self.store.read()['records'][0]['ground']['digest'])

    def test_forged_observed_count_refused_after_rehash(self):
        root=self.store.bootstrap(REPAIRABLE,6)
        self.store.observe(root['digest'],coordinate_budget=64,partition_size=16)
        image=deepcopy(self.store.read())
        entry=image['observations'][0]
        entry['result']['models']+=1
        entry['digest']=_identity(entry)
        image['digest']=_identity(image)
        with self.assertRaises(ValueError):verify_memory(image)

    def test_untrusted_timing_is_not_a_mathematical_proof(self):
        root=self.store.bootstrap(REPAIRABLE,6)
        image=deepcopy(self.store.read())
        image['records'][0]['construction_ms']=0.0
        image['records'][0]['digest']=_identity(image['records'][0])
        image['digest']=_identity(image)
        # It is only a local observation. Rehashing can change it; it never
        # grants semantics/authority or permits a false SAT conclusion.
        self.assertEqual(verify_memory(image)['qualified_constructions'],1)
        self.assertEqual(root['ground'],image['records'][0]['ground'])

    def test_96_random_source_strengthenings_preserve_exact_model_counts(self):
        self.store.bootstrap(REPAIRABLE,6)
        rng=random.Random(27001)
        for i in range(96):
            length=rng.randrange(1,5)
            ids=rng.sample(range(1,7),length)
            extra=tuple(v if rng.randrange(2) else -v for v in ids)
            target=[*REPAIRABLE,extra]
            # Limit persistent log size; prove source-preserving transformation
            # directly from retained Ground, then replay independent CNF count.
            root=self.store.read()['records'][0]
            newer=[list(c) for c in normalize(target,6)]
            derived=_rebase(root['ground'],newer)
            self.assertEqual(independent_count(derived,max_free=6),
                             reference_count(target,6),i)

    def test_file_recovery_refuses_truncated_or_rewritten_snapshot(self):
        self.store.bootstrap(REPAIRABLE,6)
        saved=self.path.read_bytes()
        self.path.write_bytes(saved[:len(saved)//2])
        with self.assertRaises(ValueError):self.store.read()
        self.path.write_bytes(saved)
        self.assertEqual(self.store.read()['records'][0]['method'],'self-refinement')

    def test_source_checked_satisfiability_and_count_are_distinct_intentions(self):
        root=self.store.bootstrap(REPAIRABLE,6)
        satisfiability=self.store.observe(root['digest'],intention='SAT',
                                         coordinate_budget=64,partition_size=16)
        count=self.store.observe(root['digest'],intention='#SAT',
                                 coordinate_budget=64,partition_size=16)
        self.assertEqual(satisfiability['result']['status'],'SAT')
        self.assertIsNone(satisfiability['result']['models'])
        self.assertLess(satisfiability['result']['checked'],count['result']['checked'])
        self.assertEqual(count['result']['models'],5)
        self.assertEqual(verify_memory(self.store.read())['source_checked_observations'],2)

    def test_cached_verified_snapshot_rejects_out_of_band_edit(self):
        root=self.store.bootstrap(REPAIRABLE,6)
        snapshot=self.store.read()
        snapshot['records'][0]['ground']['instructions'][0]['table'][0]^=1
        self.assertEqual(self.store.read()['records'][0]['ground'],root['ground'])
        # Modify the file AFTER the memory instance qualified its exact bytes.
        data=json.loads(self.path.read_text())
        data['records'][0]['construction_ms']=1.234
        data['records'][0]['digest']=_identity(data['records'][0])
        data['digest']=_identity(data)
        self.path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            self.store.extend([*REPAIRABLE,(-1,2)],6)
        # A separately constructed reader can qualify an exact complete image
        # independently, but the original writer refuses the racing edit.
        reopened=ConstructionMemory(self.path)
        self.assertEqual(len(reopened.read()['records']),1)

    def test_forged_meta_refinement_receipt_is_rejected_from_disk(self):
        self.store.bootstrap(REPAIRABLE,6)
        image=deepcopy(self.store.read())
        report=image['records'][0]['refinement_report']
        witness=next(row for row in report['meta_attempts'] if row['status']=='SAT')
        witness['witness_decimal']='0'
        report['digest']=_identity(report)
        image['records'][0]['digest']=_identity(image['records'][0])
        image['digest']=_identity(image)
        with self.assertRaises(ValueError):verify_memory(image)

    def test_no_duplicate_bootstrap_and_invalid_budgets(self):
        self.store.bootstrap(REPAIRABLE,6)
        with self.assertRaises(ValueError):self.store.bootstrap(REPAIRABLE,6)
        with self.assertRaises(ValueError):self.store.observe('f'*64)
        record=self.store.read()['records'][0]
        with self.assertRaises(ValueError):self.store.observe(record['digest'],coordinate_budget=-1)
        with self.assertRaises(ValueError):self.store.observe(record['digest'],intention='unproved')


if __name__=='__main__':unittest.main()
