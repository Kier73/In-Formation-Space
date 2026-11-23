"""OFG-001 deterministic bounded benchmark, including construction and verification."""
from __future__ import annotations

import json
from time import perf_counter

from observer_fiber_ground import (compile_ground, verify_ground, encode_observation,
                                   decode_observation, disjoint_three_state_source)


def run() -> dict:
    report = {"schema": "ifs.ofg.experiment.v1", "rows": []}
    for blocks in (8, 64, 256):
        for mode in ("constant", "parity", "identity"):
            source = disjoint_three_state_source(blocks, old_mode=mode)
            t0 = perf_counter()
            ground = compile_ground(source)
            t1 = perf_counter()
            assert verify_ground(source, ground)
            t2 = perf_counter()
            for k in range(200):
                a = sum(((k + i) % 3 in (1, 2)) << (2 * i + (1 if (k + i) % 3 == 2 else 0))
                        for i in range(blocks))
                old, supplemental = encode_observation(source, ground, a)
                recovered = decode_observation(source, ground, old, supplemental)
                assert recovered == a
            t3 = perf_counter()
            report["rows"].append({"blocks": blocks, "n": source.n, "mode": mode,
                "satisfying_assignments": str(ground["models"]),
                "state_space_bits": source.n,
                "minimum_aux_bits": ground["minimum_aux_bits"],
                "local_states_checked": ground["local_states_checked"],
                "certificate_bytes": len(json.dumps(ground, sort_keys=True, separators=(",", ":")).encode()),
                "compile_ms": round((t1-t0)*1000, 3),
                "verify_ms": round((t2-t1)*1000, 3),
                "query_200_ms": round((t3-t2)*1000, 3)})
    return report


if __name__ == "__main__":
    print(json.dumps(run(), indent=2))
