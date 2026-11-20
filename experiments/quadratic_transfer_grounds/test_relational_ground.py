"""TCN-010 adversarial, model-relative, and independent mathematical tests."""
import hashlib
import json
import unittest
from itertools import product

from relational_ground import (Action, Host, Intent, SpecificationError,
    synthesize, receipt, verify_receipt, _eval_readout, render_terminal_phase, navigate_action_counts)


def cube(*, bits=2, visible=None, safe=None, actions=None,
         hosts=None, goal=None, budget=100, probes=1024, switch=0, p=7):
    states = tuple('s' + ''.join(map(str, v)) for v in product((0,1), repeat=bits))
    values = {s: tuple(int(i) for i in s[1:]) for s in states}
    codes = {s: sum(int(v) << i for i, v in enumerate(values[s])) for s in states}
    inverse = {v: k for k,v in codes.items()}
    default = {f'toggle_{i}': 1 << i for i in range(bits)}
    if bits == 2:
        default['toggle_both'] = 3
    masks = actions if actions is not None else default
    moves = tuple(Action(name, tuple((s, inverse[codes[s] ^ mask]) for s in states))
                  for name,mask in masks.items())
    fields = tuple((s, values[s] + (sum(values[s]) % 2,)) for s in states)
    visible = tuple(range(bits)) if visible is None else visible
    safe = states if safe is None else tuple(s for s in states if safe(values[s]))
    hosts = hosts if hosts is not None else (Host('universal',tuple(masks),1),)
    goals = goal if goal is not None else tuple((i,1) for i in range(bits))
    return Intent(p, states, moves, fields, visible, safe, states[0], goals,
                  hosts, budget, probes, switch)


class RelationalTests(unittest.TestCase):
    def test_construct_two_latent_coordinates_from_unlabeled_states(self):
        spec = cube(p=7)
        r = synthesize(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['observed_classes'],4)
        self.assertEqual(r['latent_bits'],2)
        self.assertEqual(r['affine_dimension'],2)
        self.assertEqual(r['affine_lower_bound'],2)
        self.assertEqual(r['independent_generator_actions'],['toggle_0','toggle_1'])
        self.assertEqual(r['operator_diagonals']['toggle_both'],[6,6])
        self.assertEqual(r['plan']['actions'],['toggle_both'])
        self.assertEqual(r['plan']['cost'],1)
        self.assertEqual(r['goal_readout'],{'0':1,'1':1})
        # Four abstract states also fit into *one scalar field residue* (p=7).
        # Yet no one-dimensional faithful ODD-characteristic affine action exists
        # for the independent Klein-four involutions. This is not a capacity test.
        self.assertLessEqual(len(spec.states),spec.p)

    def test_all_transition_and_observer_tables_reconstructed_independently(self):
        spec = cube(p=11)
        r = synthesize(spec)
        idx={s:j for j,group in enumerate(r['quotient']) for s in group}
        for s, values in spec.outputs:
            j=idx[s]
            z=r['character_coordinates'][j]
            for channel,truth in enumerate(values):
                if channel in spec.visible_channels:
                    self.assertEqual(_eval_readout(r['observable_polynomials'][channel],z,spec.p),truth)
                else:
                    self.assertIsNone(r['observable_polynomials'][channel])
            for action in spec.actions:
                dst=dict(action.edges)[s]
                D=r['operator_diagonals'][action.name]
                got=tuple(a*b%spec.p for a,b in zip(z,D))
                self.assertEqual(got,tuple(r['character_coordinates'][idx[dst]]))

    def test_safe_invariant_generates_action_guards(self):
        spec=cube(safe=lambda v: v[0] == v[1])
        r=synthesize(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['plan']['actions'],['toggle_both'])
        guards={g['action']:g['allowed_classes'] for g in r['safety_guards']}
        self.assertEqual(guards['toggle_0'],[])
        self.assertEqual(guards['toggle_1'],[])
        self.assertEqual(len(guards['toggle_both']),2)
        self.assertTrue(all(s in spec.safe_states for s in r['plan']['states']))

    def test_unguarded_goal_unreachable_but_not_host_failure(self):
        r=synthesize(cube(actions={'toggle_0':1,'toggle_1':2},
                          safe=lambda v:v[0]==v[1]))
        self.assertEqual(r['status'],'unreachable_under_safety_guards')

    def test_declared_host_lacks_only_invariant_preserving_action(self):
        r=synthesize(cube(safe=lambda v:v[0]==v[1],
                          hosts=(Host('two-singles',('toggle_0','toggle_1'),1),)))
        self.assertEqual(r['status'],'unreachable_with_declared_hosts')
        self.assertEqual(r['witness']['mathematical_plan']['actions'],['toggle_both'])

    def test_budget_is_not_nonexistence(self):
        r=synthesize(cube(budget=0))
        self.assertEqual(r['status'],'refused_execution_budget')
        self.assertEqual(r['witness']['least_cost'],1)

    def test_observer_scope_changes_constructed_dimension(self):
        full=synthesize(cube(bits=3,p=11))
        parity=synthesize(cube(bits=3,p=11,visible=(3,),goal=((3,1),)))
        first=synthesize(cube(bits=3,p=11,visible=(0,),goal=((0,1),)))
        self.assertEqual(full['latent_bits'],3)
        self.assertEqual(full['observed_classes'],8)
        self.assertEqual(parity['latent_bits'],1)
        self.assertEqual(parity['observed_classes'],2)
        self.assertEqual(first['latent_bits'],1)
        self.assertEqual(first['operator_diagonals']['toggle_1'],[1])
        self.assertEqual(parity['goal_readout']['3'],1)

    def test_trivial_observer_zero_latent_degrees_and_vgi_one_register(self):
        # Requests on non-visible channels are deliberately rejected.
        with self.assertRaises(SpecificationError):
            cube(visible=(),goal=((0,0),))
        src=cube(bits=2,p=7)
        with self.assertRaises(SpecificationError):
            Intent(src.p,src.states,src.actions,
                   tuple((s,(3,)) for s in src.states),(),src.safe_states,src.start,
                   ((0,3),),src.hosts)
        # Make one visible constant channel (true observer quotient is one state).
        spec=Intent(src.p,src.states,src.actions,
                    tuple((s,(3,)) for s in src.states),(0,),src.safe_states,src.start,
                    ((0,3),),src.hosts)
        r=synthesize(spec)
        self.assertEqual(r['latent_bits'],0)
        self.assertEqual(r['affine_dimension'],1)
        self.assertEqual(r['observed_classes'],1)
        self.assertEqual(r['plan']['actions'],[])

    def test_noncommuting_involutions_explicit_counterexample(self):
        states=('x','y','z')
        a=Action('a',(('x','y'),('y','x'),('z','z')))
        b=Action('b',(('x','x'),('y','z'),('z','y')))
        spec=Intent(7,states,(a,b),tuple((s,(i,)) for i,s in enumerate(states)),
                    (0,),states,'x',((0,2),),(Host('h',('a','b')),))
        r=synthesize(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['family'],'onehot')
        self.assertEqual(r['affine_dimension'],3)
        self.assertEqual(r['plan']['states'][-1],'z')
        denied=Intent(**{**spec.__dict__,'enable_onehot':False})
        r=synthesize(denied)
        self.assertEqual(r['status'],'unsupported_action_algebra')
        self.assertEqual(r['witness']['kind'],'noncommuting')

    def test_noninvolution_is_outside_the_declared_family(self):
        states=('a','b','c')
        op=Action('next',(('a','b'),('b','c'),('c','a')))
        spec=Intent(7,states,(op,),tuple((s,(i,)) for i,s in enumerate(states)),
                    (0,),states,'a',((0,2),),(Host('h',('next',)),))
        r=synthesize(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['family'],'onehot')
        denied=Intent(**{**spec.__dict__,'enable_onehot':False})
        r=synthesize(denied)
        self.assertEqual(r['status'],'unsupported_action_algebra')
        self.assertEqual(r['witness']['kind'],'not_involution')

    def test_nontransitive_rejected_with_witness(self):
        states=('a','b','c','d')
        op=Action('swap',(('a','b'),('b','a'),('c','d'),('d','c')))
        spec=Intent(7,states,(op,),tuple((s,(i,)) for i,s in enumerate(states)),
                    (0,),states,'a',((0,3),),(Host('h',('swap',)),))
        r=synthesize(spec)
        self.assertEqual(r['status'],'unreachable_under_safety_guards')
        self.assertEqual(r['family'],'onehot')
        denied=Intent(**{**spec.__dict__,'enable_onehot':False})
        r=synthesize(denied)
        self.assertEqual(r['status'],'unsupported_nontransitive_orbit')
        self.assertEqual(len(r['witness']['orbit_classes']),2)

    def test_insufficient_search_budget_refuses_unknown(self):
        spec=cube(bits=3,probes=4)
        r=synthesize(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['family'],'onehot')
        self.assertEqual(r['affine_dimension'],8)
        denied=Intent(**{**spec.__dict__,'enable_onehot':False})
        r=synthesize(denied)
        self.assertEqual(r['status'],'refused_search_budget')
        self.assertEqual(r['required_group_probes'],8)

    def test_host_switching_cost_changes_optimal_placement(self):
        spec=cube(bits=3, goal=((0,1),(1,1)),
                  hosts=(Host('x',('toggle_0',),1),
                         Host('y',('toggle_1',),1),
                         Host('both',('toggle_0','toggle_1'),3)),switch=5)
        r=synthesize(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['plan']['cost'],6)
        self.assertEqual(r['plan']['hosts'],['both','both'])

    def test_absolutely_no_host_for_goal_but_unrestricted_math_exists(self):
        spec=cube(hosts=(Host('only-x',('toggle_0',),1),),goal=((1,1),))
        r=synthesize(spec)
        self.assertEqual(r['status'],'unreachable_with_declared_hosts')

    def test_refuses_incomplete_observations_and_action_edges(self):
        source=cube()
        bad=Action('broken',source.actions[0].edges[:-1])
        with self.assertRaises(SpecificationError):
            Intent(source.p,source.states,(bad,),source.outputs,source.visible_channels,
                   source.safe_states,source.start,source.goal,source.hosts)

    def test_exact_result_is_stable_under_state_renaming(self):
        src=cube(bits=3,p=11)
        rename={s:'NODE_'+str(i) for i,s in enumerate(reversed(src.states))}
        other=Intent(src.p,tuple(rename[s] for s in reversed(src.states)),
                     tuple(Action(a.name,tuple((rename[x],rename[y]) for x,y in a.edges)) for a in src.actions),
                     tuple((rename[s],v) for s,v in src.outputs),src.visible_channels,
                     tuple(rename[s] for s in src.safe_states),rename[src.start],src.goal,src.hosts)
        a,b=synthesize(src),synthesize(other)
        self.assertEqual(a['latent_bits'],b['latent_bits'])
        self.assertEqual(a['plan']['cost'],b['plan']['cost'])
        self.assertEqual(a['goal_readout'],b['goal_readout'])

    def test_receipt_is_recomputed_even_with_reforged_hash(self):
        spec=cube(p=7)
        claim=receipt(spec)
        self.assertTrue(verify_receipt(spec,json.loads(json.dumps(claim))))
        forged=json.loads(json.dumps(claim))
        forged['result']['operator_diagonals']['toggle_0']=[1,1]
        body={k:forged[k] for k in ('schema','intention','result')}
        forged['sha256']=hashlib.sha256(json.dumps(body,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        self.assertFalse(verify_receipt(spec,forged))
        self.assertFalse(verify_receipt(cube(budget=0),claim))

    def test_existing_tcn008_phase_renderer_reused(self):
        from intention_ground import Host as PhaseHost, verify_receipt as verify_phase
        spec=cube(p=7)
        r=synthesize(spec)
        phase=render_terminal_phase(spec,r,(PhaseHost('phase',3,(1,),1,1,5,100),))
        self.assertEqual(phase['status'],'realizable')
        self.assertEqual(phase['relative_phase_slope'],1)
        self.assertTrue(verify_phase(phase['phase_receipt']))

    def test_unselected_channel_not_falsely_compiled(self):
        spec=cube(bits=3,p=11,visible=(3,),goal=((3,1),))
        r=synthesize(spec)
        self.assertEqual(r['latent_bits'],1)
        self.assertEqual(r['observable_scope']['unselected_channels'],[0,1,2])
        self.assertEqual(r['observable_polynomials'][:3],[None,None,None])
        # There exist states merged by parity but differing in individual bits.
        self.assertTrue(any(len(group)>1 for group in r['quotient']))

    def test_eight_dimensions_recovered_from_256_named_states(self):
        spec=cube(bits=8,p=11,goal=((0,1),(7,1)))
        r=synthesize(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['affine_dimension'],8)
        self.assertEqual(r['group_elements_constructed'],256)
        self.assertEqual(r['observed_classes'],256)
        self.assertEqual(r['plan']['cost'],2)

    def test_noncommuting_onehot_matrices_execute_exactly(self):
        states=('x','y','z')
        a=Action('a',(('x','y'),('y','x'),('z','z')))
        b=Action('b',(('x','x'),('y','z'),('z','y')))
        spec=Intent(7,states,(a,b),tuple((s,(i,)) for i,s in enumerate(states)),
                    (0,),states,'x',((0,2),),(Host('h',('a','b')),))
        r=synthesize(spec)
        self.assertEqual(r['family'],'onehot')
        labels={s:j for j,block in enumerate(r['quotient']) for s in block}
        for action in spec.actions:
            matrix=r['operator_matrices'][action.name]
            for left,right in action.edges:
                old=r['coordinates'][labels[left]]
                new=[sum(a*x for a,x in zip(row,old))%7 for row in matrix]
                self.assertEqual(new,r['coordinates'][labels[right]])
        self.assertEqual(r['minimality_scope'][:2],'NO')

    def test_character_host_missing_but_onehot_host_available(self):
        spec=cube(hosts=(Host('legacy',('toggle_0','toggle_1','toggle_both'),
                               1,('onehot',),4),))
        r=synthesize(spec)
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['family'],'onehot')
        self.assertEqual(r['affine_dimension'],4)
        self.assertTrue(verify_receipt(spec,receipt(spec)))

    def test_brute_force_affine_one_dim_obstruction_not_capacity(self):
        # Exhaust every injection of Klein four states into F7 as scalars.
        # Each swap fixes an affine reflection uniquely from two point pairs.
        from itertools import permutations
        p=7
        viable=0
        for x00,x10,x01,x11 in permutations(range(p),4):
            a=lambda x:(-x+x00+x10)%p
            b=lambda x:(-x+x00+x01)%p
            if (a(x01)==x11 and a(x11)==x01 and
                b(x10)==x11 and b(x11)==x10):
                viable+=1
        self.assertEqual(viable,0)
        # A one-dimensional arbitrary LOOKUP would fit four distinct residues;
        # the obstruction is specifically faithful affine action in odd char.

    def test_nonbijective_action_is_representable_by_functional_onehot(self):
        states=('x','y','z')
        op=Action('reset',(('x','x'),('y','x'),('z','x')))
        spec=Intent(7,states,(op,),tuple((s,(i,)) for i,s in enumerate(states)),
                    (0,),states,'y',((0,0),),(Host('h',('reset',)),))
        r=synthesize(spec)
        self.assertEqual(r['family'],'onehot')
        self.assertEqual(r['status'],'realizable')
        self.assertEqual(r['plan']['actions'],['reset'])
        matrix=r['operator_matrices']['reset']
        self.assertEqual([sum(row) for row in matrix],[3,0,0])

    def test_hundred_digit_commuting_action_jump_and_guard_refusal(self):
        from relational_ground import navigate_action_counts
        spec=cube(p=7)
        r=synthesize(spec)
        jump=navigate_action_counts(spec,r,{'toggle_0':10**100+1,'toggle_1':10**99+1})
        self.assertTrue(jump['goal_satisfied'])
        self.assertEqual(jump['observed_outputs']['0'],1)
        self.assertEqual(jump['observed_outputs']['1'],1)
        self.assertEqual(jump['modular_products'],4)
        guarded=cube(safe=lambda v:v[0]==v[1])
        with self.assertRaisesRegex(SpecificationError,'unsafe grouped'):
            navigate_action_counts(guarded,synthesize(guarded),{'toggle_0':10**100})

    def test_other_prime_independent_oracle(self):
        for p in (3,5,7,11,31,127):
            spec=cube(p=p)
            r=synthesize(spec)
            self.assertEqual(r['status'],'realizable')
            self.assertEqual(r['affine_dimension'],2)
            for action in spec.actions:
                diag=r['operator_diagonals'][action.name]
                self.assertTrue(all(z in (1,p-1) for z in diag))


if __name__=='__main__':
    unittest.main()
