"""Self-contained verification & counterexample suite for Fluid In-Transit Computation (FIT-001)."""

from __future__ import annotations

import json
import math
from typing import Sequence
import unittest


def tropical_matmul(a: Sequence[Sequence[float]], b: Sequence[Sequence[float]]) -> list[list[float]]:
    d = len(a)
    return [[min(a[i][k] + b[k][j] for k in range(d)) for j in range(d)] for i in range(d)]


def flash_monoid_combine(
    state_a: tuple[float, float, list[float]],
    state_b: tuple[float, float, list[float]],
) -> tuple[float, float, list[float]]:
    ma, la, oa = state_a
    mb, lb, ob = state_b
    if la == 0.0:
        return (mb, lb, list(ob))
    if lb == 0.0:
        return (ma, la, list(oa))
    m_new = max(ma, mb)
    sa, sb = math.exp(ma - m_new), math.exp(mb - m_new)
    return (m_new, sa * la + sb * lb, [sa * x + sb * y for x, y in zip(oa, ob)])


class TestFluidInTransitStudy(unittest.TestCase):
    def test_tropical_dp_associativity_vs_sequential_steps(self) -> None:
        w1 = [[0.0, 3.0, math.inf], [2.0, 0.0, 1.5], [4.0, 1.0, 0.0]]
        w2 = [[0.0, 1.0, 6.0], [math.inf, 0.0, 2.0], [0.5, 3.0, 0.0]]
        w3 = [[0.0, 2.5, 1.0], [1.0, 0.0, 4.0], [2.0, 0.5, 0.0]]
        left_fold = tropical_matmul(tropical_matmul(w1, w2), w3)
        right_fold = tropical_matmul(w1, tropical_matmul(w2, w3))
        for r1, r2 in zip(left_fold, right_fold):
            for x, y in zip(r1, r2):
                self.assertAlmostEqual(x, y, places=12)

    def test_flash_stream_monoid_exactness_and_premature_normalization_counterexample(self) -> None:
        q = [1.2, -0.7]
        shards = [
            ([[0.5, 0.2], [-1.0, 0.4]], [[1.0, 2.0], [3.0, 4.0]]),
            ([[1.5, -0.5]], [[10.0, 20.0]]),
            ([[-0.3, 0.9], [0.8, -1.1]], [[5.0, 6.0], [7.0, 8.0]]),
        ]
        # Stream hop-by-hop using only (m, l, O)
        state = (-math.inf, 0.0, [0.0, 0.0])
        naive_local_avgs: list[list[float]] = []
        all_k, all_v = [], []
        scale = 1.0 / math.sqrt(2.0)
        for ks, vs in shards:
            all_k.extend(ks)
            all_v.extend(vs)
            scores = [sum(a * b for a, b in zip(q, k)) * scale for k in ks]
            m_loc = max(scores)
            exps = [math.exp(s - m_loc) for s in scores]
            l_loc = sum(exps)
            o_loc = [sum(w * v[d] for w, v in zip(exps, vs)) for d in range(2)]
            state = flash_monoid_combine(state, (m_loc, l_loc, o_loc))
            naive_local_avgs.append([x / l_loc for x in o_loc])

        stream_final = [x / state[1] for x in state[2]]
        # Compare against full materialized softmax over all keys
        full_scores = [sum(a * b for a, b in zip(q, k)) * scale for k in all_k]
        m_full = max(full_scores)
        full_exps = [math.exp(s - m_full) for s in full_scores]
        full_out = [sum(w * v[d] for w, v in zip(full_exps, all_v)) / sum(full_exps) for d in range(2)]
        for a, b in zip(stream_final, full_out):
            self.assertAlmostEqual(a, b, places=10)

        # Negative control: averaging locally normalized shard outputs fails badly!
        premature = [sum(loc[d] for loc in naive_local_avgs) / len(naive_local_avgs) for d in range(2)]
        self.assertGreater(abs(stream_final[1] - premature[1]), 1.0)

    def test_virtual_memory_pullback_commutation_saves_bytes(self) -> None:
        base = bytes((29 * i + 7) % 256 for i in range(2048))
        patches = {13: 240, 1024: 11}  # Logical indices after transpose(32, 64) + reverse
        # Materialize reference: transpose(32, 64) -> reverse -> apply patches
        transposed = bytearray(2048)
        for r in range(32):
            for c in range(64):
                transposed[c * 32 + r] = base[r * 64 + c]
        rev = bytearray(reversed(transposed))
        for idx, val in patches.items():
            rev[idx] = val

        # Pullback sum without permuting buffer: map patched logical index back to base index!
        def inv_index(log_idx: int) -> int:
            after_trans = 2047 - log_idx
            c, r = divmod(after_trans, 32)
            return r * 64 + c

        pullback_sum = sum(base) + sum(val - base[inv_index(i)] for i, val in patches.items())
        self.assertEqual(pullback_sum, sum(rev))
        descriptor = json.dumps({"base_len": 2048, "ops": [["transpose", 32, 64], ["reverse"]], "patches": list(patches.items())})
        self.assertLess(len(descriptor.encode("utf-8")), 128)


if __name__ == "__main__":
    unittest.main()
