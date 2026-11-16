"""AKS-002 tests: multi-head, multi-layer, associative segments, native adapters."""
from __future__ import annotations

import importlib.util
import os
import random
import sys
import unittest
from dataclasses import replace

from attention_ground import AttentionGround, GroundRefused, PrefixGround, TokenEvidence, direct_observe
from composed_attention import (
    Head, Layer, Network, CausalState, InputEvidence, segment_from_tokens,
    direct_history_reference, independently_verify_trace, native_ecpu_dag_snapshot,
    vgi_operator_crosscheck, checkpoint, restore_checkpoint, verify_segment,
)


def demo_network(layer_count=3, head_count=3, *, normalized=True):
    # Source x=(1, variable, transformed_value). Two leading coordinates are
    # preserved by every residual output; the third is transformed across layers.
    heads = (
        Head(((0, 1, 0),), ((1, 0, 0),), ((0, 0, 1),)),
        Head(((1, 0, 0),), ((0, 1, 0),), ((0, 0, 1), (1, 0, 0))),
        Head(((1, 0, 0),), ((1, 0, 0),), ((0, 1, 0),)),
    )[:head_count]
    value_dim = sum(len(h.value) for h in heads)
    # Project first and last head values only to third coordinate.
    weights = tuple((0,) * value_dim for _ in range(2)) + \
              (tuple((i + 1) % 5 for i in range(value_dim)),)
    return Network(65521, 3, tuple(Layer(heads, weights, normalized) for _ in range(layer_count)))


def run_network(network, count):
    state = CausalState.empty(network)
    tokens = []
    receipts = []
    for i in range(count):
        token = InputEvidence.form(network, i, state.source_head,
                                   (1, i % 7, (3*i + i*i) % 23))
        state, receipt = state.advance(token)
        tokens.append(token)
        receipts.append(receipt)
    return state, tokens, receipts


class NativeComposedAttentionTests(unittest.TestCase):
    def test_multihead_three_layer_causal_reference(self):
        network = demo_network()
        state, tokens, receipts = run_network(network, 120)
        self.assertEqual(state.count, 120)
        self.assertEqual(len(state.prefixes), 3)
        self.assertTrue(all(len(row) == 3 for row in state.prefixes))
        self.assertEqual(tuple(x.output for x in receipts), direct_history_reference(network, tokens))
        self.assertEqual(independently_verify_trace(
            network, tokens, receipts, expected_source_head=state.source_head,
            expected_state_digest=state.fingerprint), state)
        self.assertNotEqual(receipts[0].output, receipts[-1].output)

    def test_four_thousand_steps_fixed_state_shape(self):
        network = demo_network(3, 3, normalized=False)
        state, _tokens, _receipts = run_network(network, 4000)
        self.assertEqual(state.count, 4000)
        for layer, spec in zip(state.prefixes, network.layers):
            for prefix, head in zip(layer, spec.heads):
                self.assertEqual(len(prefix.matrix), len(head.key)+1)
                self.assertEqual(len(prefix.matrix[0]), len(head.value))
        self.assertEqual(len(state.fingerprint), 64)

    def test_normalized_rejects_invalid_field_denominator(self):
        network = Network(5, 1, (Layer((Head(((0,),), ((0,),), ((1,),)),),
                                       ((1,),), True),))
        state = CausalState.empty(network)
        for i in range(4):
            state, _ = state.advance(InputEvidence.form(network, i, state.source_head, (1,)))
        # Each token has kernel 1; adding the fifth makes denominator 0 mod 5.
        with self.assertRaisesRegex(GroundRefused, "denominator"):
            state.advance(InputEvidence.form(network, 4, state.source_head, (1,)))
        self.assertEqual(state.count, 4)

    def test_strict_construction_and_source_lineage_refusal(self):
        g = demo_network(1,1)
        with self.assertRaises(GroundRefused):
            Network(15,3,g.layers)
        with self.assertRaises(GroundRefused):
            Network(65521,3,(Layer((Head(((1,2,3),),((1,2,3),(0,1,0)),((1,2,3),)),),((1,),)*3),))
        state, tokens, receipts = run_network(g, 12)
        with self.assertRaisesRegex(GroundRefused, "source"):
            independently_verify_trace(g, tokens, receipts, expected_source_head="f"*64,
                                       expected_state_digest=state.fingerprint)
        edited = replace(tokens[3], vector=(1,2,3))
        with self.assertRaises(GroundRefused):
            independently_verify_trace(g, [*tokens[:3], edited, *tokens[4:]], receipts,
                                       expected_source_head=state.source_head,
                                       expected_state_digest=state.fingerprint)
        with self.assertRaisesRegex(GroundRefused, "receipt"):
            independently_verify_trace(g, tokens, [*receipts[:3], replace(receipts[3], output=(1,2,3)),
                                                    *receipts[4:]],
                                       expected_source_head=state.source_head,
                                       expected_state_digest=state.fingerprint)

    def test_partitioned_moments_associativity_and_naive_observation(self):
        g = AttentionGround(65521,2,3)
        state = PrefixGround.empty(g)
        tokens = []
        for i in range(513):
            tok = TokenEvidence.form(g, i, state.history_head,
                                     (i % 11, i % 17), (i % 23, (i*i) % 37, i % 5))
            state = state.admit(tok)
            tokens.append(tok)
        segments = [segment_from_tokens(g, tokens[a:b]) for a,b in
                    ((0,103),(103,224),(224,363),(363,513))]
        left = segments[0].combine(segments[1]).combine(segments[2]).combine(segments[3])
        right = segments[0].combine(segments[1].combine(segments[2].combine(segments[3])))
        self.assertEqual(left, right)
        self.assertEqual((left.matrix,left.mass,left.head),
                         (state.matrix,state.mass,state.history_head))
        for q in ((0,0),(1,2),(15,20)):
            for norm in (True,False):
                self.assertEqual(left.query(q,normalized=norm),
                                 direct_observe(g,tokens,q,normalized=norm))

    def test_segment_refuses_reorder_and_altered_evidence(self):
        g = AttentionGround(101,1,1)
        state = PrefixGround.empty(g)
        tokens = []
        for i in range(12):
            t = TokenEvidence.form(g,i,state.history_head,(i,),(3*i,))
            state = state.admit(t)
            tokens.append(t)
        a = segment_from_tokens(g,tokens[:5]); b = segment_from_tokens(g,tokens[5:])
        with self.assertRaisesRegex(GroundRefused,'adjacent'):
            b.combine(a)
        with self.assertRaisesRegex(GroundRefused,'discontinuous'):
            segment_from_tokens(g,tokens[1:5]+tokens[:1])
        with self.assertRaises(GroundRefused):
            segment_from_tokens(g, [replace(tokens[0],value=(99,)), *tokens[1:]])
        with self.assertRaises(GroundRefused):
            segment_from_tokens(g, [])

    def test_compositional_versus_full_history_cost_growth(self):
        network=demo_network(2,2,normalized=False)
        # A correctness comparison only: estimated algebraic work, not timings.
        for n in (8,32,96):
            state,tokens,receipts=run_network(network,n)
            self.assertEqual(tuple(r.output for r in receipts),direct_history_reference(network,tokens))
            self.assertTrue(all(len(row)==2 for row in state.prefixes))
        self.assertGreater(96*97//2, 96)

    def test_checkpoint_restarts_without_historical_tokens(self):
        network = demo_network(3,3)
        uninterrupted, inputs, receipts = run_network(network, 177)
        intermediate = CausalState.empty(network)
        for token in inputs[:89]:
            intermediate, _ = intermediate.advance(token)
        packed = checkpoint(intermediate)
        recovered = restore_checkpoint(network, packed,
                                       expected_source_head=intermediate.source_head,
                                       expected_state_digest=intermediate.fingerprint)
        self.assertEqual(recovered, intermediate)
        for token in inputs[89:]:
            recovered, _ = recovered.advance(token)
        self.assertEqual(recovered, uninterrupted)
        changed = {**packed, "count": 90}
        with self.assertRaises(GroundRefused):
            restore_checkpoint(network, changed, expected_source_head=intermediate.source_head,
                               expected_state_digest=intermediate.fingerprint)
        with self.assertRaisesRegex(GroundRefused,'receiver-owned'):
            restore_checkpoint(network, packed, expected_source_head='f'*64,
                               expected_state_digest=intermediate.fingerprint)

    def test_segment_independent_verifier_rejects_rehashed_false_moments(self):
        g=AttentionGround(101,1,1)
        state=PrefixGround.empty(g); tokens=[]
        for i in range(9):
            tok=TokenEvidence.form(g,i,state.history_head,(i,),(i*3,))
            state=state.admit(tok); tokens.append(tok)
        seg=segment_from_tokens(g,tokens)
        self.assertTrue(verify_segment(g,tokens,seg,expected_head=state.history_head))
        corrupt=replace(seg, matrix=((42,), seg.matrix[1]))
        with self.assertRaisesRegex(GroundRefused,'source-derived'):
            verify_segment(g,tokens,corrupt,expected_head=state.history_head)
        with self.assertRaisesRegex(GroundRefused,'receiver-owned'):
            verify_segment(g,tokens,seg,expected_head='f'*64)

    @unittest.skipUnless(importlib.util.find_spec('vgi') is not None, 'native VGI not installed locally')
    def test_reuses_actual_vgi_typed_operator_semantics(self):
        network=demo_network(3,3)
        self.assertEqual(vgi_operator_crosscheck(network,(1,2,3)), 3*(3*3+1))

    @unittest.skipUnless(importlib.util.find_spec('mailcpu') is not None, 'native E-CPU not installed locally')
    def test_reuses_actual_ecpu_navigable_dag_frontiers_and_recovery(self):
        g=demo_network(3,3)
        _state,tokens,receipts=run_network(g,12)
        result=native_ecpu_dag_snapshot(g,receipts[-1])
        self.assertEqual(len(result['committed_nodes']), 1+3*(3+1))
        self.assertEqual(result['terminal_output'],list(receipts[-1].output))


if __name__ == '__main__':
    unittest.main()
