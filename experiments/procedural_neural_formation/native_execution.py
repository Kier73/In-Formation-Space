"""PNF-003: verified generated capsules executed by TCR's native E-CPU cuts.

The receiver constructs all four cuts from the admitted capsule. Neither a
sender-provided shard manifest nor a sender-provided capability is accepted.
"""
from __future__ import annotations

from pathlib import Path
import tempfile

import numpy as np

from experiments.tensor_cut_realization import tensor_cut as tcr
from experiments.tensor_cut_realization import transit_tensor as tr
from experiments.tensor_cut_realization.native_admission import NativeCut, accept_partition

from .capsule import unpack_pair, verify_capsule
from .formation import FormationError, evaluate
from .verification import scalar_oracle


def execute_capsule(raw: bytes, policy: dict, *, grant_compute: bool = True) -> dict:
    """Verify, locally provision, authorize and compare four native contributions.

This bounded experiment uses TCR's two fixed probes, independently of the
capsule's verification probes. Replay is within the same live E-CPU runtime.
Verification/reference evaluation can occur even when native compute is denied.
"""
    if type(grant_compute) is not bool:
        raise FormationError("receiver compute policy must be boolean")
    verified = verify_capsule(raw, policy)
    source, generated, _ = unpack_pair(raw, policy)
    inputs, hidden, outputs = generated.validate()
    # TCR's hex-encoded operation requests/responses each have a 100 kB cap.
    # Bound the independent scalar reference before preparation as well.
    if (hidden < 4 or 32 * max(inputs, outputs) + 8192 > tr.MAX_REQUEST
            or 2 * hidden * (inputs + min(outputs, 3)) > 12_000_000):
        raise FormationError("native cut shape/work budget exceeded")
    provenance = {"kind": "verified-pnf-generated-realization",
                  "capsule_sha256": policy["capsule_sha256"],
                  "observed_or_procedural_parent_digest": policy["source_digest"],
                  "generated_digest": policy["generated_digest"],
                  "coefficient_law": verified["coefficient_law"]}
    with tempfile.TemporaryDirectory(prefix="pnf-native-") as temporary:
        root = Path(temporary)
        prepared, results = root / "prepared", root / "results"
        manifest = tcr.prepare(generated, provenance, prepared, partitions=4)
        if manifest["source_digest"] != policy["generated_digest"]:
            raise FormationError("TCR source must be the admitted generated model")
        with np.load(prepared / "reference.npz", allow_pickle=False) as archive:
            x = archive["inputs"].copy()
        decisions = []
        for index in range(4):
            # Packets are created here, inside receiver authority, after admission.
            host = NativeCut(prepared / f"shard-{index}", grant_compute=grant_compute)
            if host.manifest != manifest or host.index != index:
                raise FormationError("receiver cut identity changed during provisioning")
            request = tr.request_for(manifest, index, x, request_id=f"pnf003-part-{index}")
            first = host.execute(request, sequence=1)
            if not grant_compute:
                if (first["accepted"] or first["hypervisor_action"] != "deny"
                        or first["executed"] or host.calls != 0):
                    raise FormationError("native compute denial failed")
                decisions.append({"index": index, "action": "deny", "handler_calls": 0,
                                  "receiver_node": host.node_id})
                continue
            if (not first["accepted"] or first["hypervisor_action"] != "allow"
                    or first["native_replayed"] or host.calls != 1):
                raise FormationError("native receiver did not execute exactly once")
            accept_partition(manifest, request, first, results)
            second = host.execute(request, sequence=1)
            if (not second["accepted"] or not second["native_replayed"] or host.calls != 1
                    or any(second[k] != first[k] for k in
                           ("event_fingerprint", "request_sha256", "partial_hex", "receipt"))):
                raise FormationError("native exact replay changed the result or recomputed")
            decisions.append({"index": index, "action": "allow", "handler_calls": host.calls,
                              "receiver_node": host.node_id,
                              "native_replayed": True,
                              "contract_digest": first["operator_contract_digest"],
                              "ground_digest": first["ground_digest"],
                              "event_fingerprint": first["event_fingerprint"],
                              "request_sha256": first["request_sha256"],
                              "partial_digest": first["receipt"]["output_digest"]})
        report = {"schema": "ifs.pnf.native-realization.v1",
                  "status": "executed" if grant_compute else "denied",
                  **policy, "manifest_digest": manifest["digest"],
                  "cut_model_digest": manifest["source_digest"],
                  "activation": generated.activation,
                  "generated_dimensions": [inputs, hidden, outputs],
                  "decisions": decisions, "native_runtime_count": 4,
                  "native_handler_calls": sum(d["handler_calls"] for d in decisions),
                  "probe_origin": "receiver-owned TCR fixed probes",
                  "native_cuts_cross_process": False, "durable_replay": False,
                  "kernel_accepted": False}
        if not grant_compute:
            return report
        aggregate = tcr.aggregate(prepared, results, root / "dag.json")
        total = np.zeros((len(x), outputs), dtype=np.float64)
        for index in range(4):
            total += tcr._accept(manifest, results, index)[0]
        total += generated.down_bias.astype(np.float64)
        if tcr._typed_digest(total) != aggregate["result_digest"]:
            raise FormationError("reconstructed output differs from DAG result")
        selected = sorted({0, outputs // 2, outputs - 1})
        report.update({"numerical_verification": aggregate["verification"],
                       "distinct_ground_content_digests": len({d["ground_digest"] for d in decisions}),
                       "max_abs_parent_dense_error": tcr._compare(total, evaluate(source, x), "native vs parent dense"),
                       "max_abs_parent_scalar_error": tcr._compare(
                           total[:, selected], scalar_oracle(source, x, selected), "native vs parent scalar"),
                       "output_digest": aggregate["result_digest"],
                       "output_coordinates_checked": int(total.size),
                       "scalar_coordinates_checked": len(x) * len(selected),
                       "input_digest": manifest["input_digest"],
                       "dag_restoration_equal": aggregate["dag_restoration_equal"],
                       "dag_snapshot": aggregate["dag_snapshot"]})
        return report
