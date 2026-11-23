"""OFG-002 deterministic benchmark and cost ledger (no implicit network execution)."""
from __future__ import annotations

import json
import platform
import statistics
from time import perf_counter_ns

from separator_fiber_ground import (compile_ground, verify_ground, shared_switch_source,
                                    encode_observation, decode_observation,
                                    old_coordinates, new_coordinates, source_accepts)


def ms(fn):
    start = perf_counter_ns()
    result = fn()
    return result, (perf_counter_ns() - start) / 1e6


def run():
    rows = []
    for blocks in (8, 32, 128, 256):
        for visible in (True, False):
            source = shared_switch_source(blocks, separator_visible=visible)
            ground, compile_ms = ms(lambda: compile_ground(source))
            accepted, verify_ms = ms(lambda: verify_ground(source, ground))
            assert accepted
            assignment = sum(1 << i for i in range(2, blocks + 1, 3))
            assert source_accepts(source, assignment)
            latency = []
            for _ in range(5):
                (old, code), enc_ms = ms(lambda: encode_observation(source, ground, assignment))
                decoded, dec_ms = ms(lambda: decode_observation(source, ground, old, code))
                assert old_coordinates(source, decoded) == old
                assert new_coordinates(source, decoded) == new_coordinates(source, assignment)
                latency.append((enc_ms, dec_ms))
            rows.append({"blocks": blocks, "source_variables": source.n,
                         "separator_visible": visible, "source_models": str(ground["models"]),
                         "distinct_new_per_largest_old_fiber": str(ground["maximum_fiber_size"]),
                         "minimum_aux_bits": ground["minimum_aux_bits"],
                         "local_states_checked": ground["local_states_checked"],
                         "certificate_bytes": len(json.dumps(ground, sort_keys=True, separators=(",", ":")).encode()),
                         "compile_ms": round(compile_ms, 4), "independent_verify_ms": round(verify_ms, 4),
                         "encode_median_ms": round(statistics.median(v[0] for v in latency), 4),
                         "decode_median_ms": round(statistics.median(v[1] for v in latency), 4)})
    return {"schema": "ifs.ofg.separator-fiber.benchmark.v1", "python": platform.python_version(),
            "platform": platform.system(), "note": "one local run; compare semantic work, not CPU rankings",
            "rows": rows}


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
