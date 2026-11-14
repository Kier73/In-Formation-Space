"""Wire-format admission, certificate controls and independent reconstruction."""
import base64
import copy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from .capsule import MAGIC, PREFIX, MAX_HEADER, canonical, pack_pair, sha, unpack_pair, verify_capsule
from .formation import FormationError, procedural_block, widen, evaluate
from .receiver import Assembly, CHUNK


def rewrite(raw, mutate_header=lambda h: None, mutate_payload=lambda b: b):
    _, length = PREFIX.unpack_from(raw)
    header = json.loads(raw[PREFIX.size:PREFIX.size + length])
    mutate_header(header)
    encoded = canonical(header)
    return PREFIX.pack(MAGIC, len(encoded)) + encoded + mutate_payload(raw[PREFIX.size + length:])


def rehash(raw, policy):
    return {**policy, "capsule_sha256": sha(raw), "capsule_bytes": len(raw)}


class CapsuleTests(unittest.TestCase):
    def setUp(self):
        self.source = procedural_block(4, 16, 4)
        self.child, self.certificate = widen(self.source, 24)
        self.raw, self.policy = pack_pair(self.source, self.child, self.certificate,
            {"kind": "procedural", "seed": 31}, [[0, 1, -2, 3]])

    def test_roundtrip_every_parameter_and_identity(self):
        source, child, header = unpack_pair(self.raw, self.policy)
        self.assertEqual(source.descriptor(), self.source.descriptor())
        self.assertEqual(child.descriptor(), self.child.descriptor())
        self.assertEqual(header["generated_origin"], "constructed-by-dyadic-widening")
        np.testing.assert_array_equal(evaluate(child, np.ones((1, 4))), evaluate(self.child, np.ones((1, 4))))

    def test_receiver_does_not_call_parameter_generators(self):
        with patch("experiments.procedural_neural_formation.formation.widen", side_effect=AssertionError), \
             patch("experiments.procedural_neural_formation.formation.procedural_block", side_effect=AssertionError):
            result = verify_capsule(self.raw, self.policy)
        self.assertEqual(result["status"], "verified")
        self.assertFalse(result["kernel_accepted"])

    def test_export_replay_requires_independent_model_pins(self):
        from .replay_export import replay
        with tempfile.TemporaryDirectory() as directory:
            capsule, policy = Path(directory) / "model.pnf", Path(directory) / "policy.json"
            capsule.write_bytes(self.raw)
            policy.write_text(json.dumps(self.policy))
            result = replay(capsule, policy, expected_source=self.policy["source_digest"],
                            expected_generated=self.policy["generated_digest"])
            self.assertEqual(result["verification"]["status"], "verified")
            with self.assertRaisesRegex(FormationError, "independently configured"):
                replay(capsule, policy, expected_source="0" * 64,
                       expected_generated=self.policy["generated_digest"])

    def test_both_activations_survive(self):
        source = replace(self.source, activation="relu")
        child, certificate = widen(source, 32)
        raw, policy = pack_pair(source, child, certificate, {"kind": "procedural"}, [[-1, 2, -3, 4]])
        self.assertEqual(verify_capsule(raw, policy)["activation"], "relu")

    def test_architecture_alone_does_not_identify_parameters_or_behavior(self):
        alternative = procedural_block(4, 16, 4, seed=32)
        self.assertEqual(alternative.validate(), self.source.validate())
        self.assertNotEqual(alternative.descriptor()["digest"], self.source.descriptor()["digest"])
        self.assertFalse(np.array_equal(evaluate(alternative, np.ones((1, 4))), evaluate(self.source, np.ones((1, 4)))))

    def test_outer_digest_and_external_source_pins(self):
        with self.assertRaisesRegex(FormationError, "capsule identity"):
            unpack_pair(self.raw[:-1] + bytes([self.raw[-1] ^ 1]), self.policy)
        with self.assertRaisesRegex(FormationError, "model identity"):
            unpack_pair(self.raw, {**self.policy, "source_digest": "a" * 64})

    def test_rehashed_payload_still_needs_tensor_digests(self):
        raw = rewrite(self.raw, mutate_payload=lambda p: p[:-1] + bytes([p[-1] ^ 1]))
        with self.assertRaisesRegex(FormationError, "tensor payload"):
            unpack_pair(raw, rehash(raw, self.policy))

    def test_rehashed_trailing_or_missing_bytes(self):
        for raw in (self.raw + b"x", self.raw[:-1]):
            with self.assertRaisesRegex(FormationError, "truncated or trailing"):
                unpack_pair(raw, rehash(raw, self.policy))

    def test_bad_magic_or_oversize_header(self):
        for raw in (b"XXXXXXXX" + self.raw[8:], PREFIX.pack(MAGIC, MAX_HEADER + 1) + self.raw[PREFIX.size:]):
            with self.assertRaisesRegex(FormationError, "prefix"):
                unpack_pair(raw, rehash(raw, self.policy))

    def test_duplicate_json_key(self):
        _, length = PREFIX.unpack_from(self.raw)
        h = self.raw[PREFIX.size:PREFIX.size + length]
        h = b'{"schema":"duplicate",' + h[1:]
        raw = PREFIX.pack(MAGIC, len(h)) + h + self.raw[PREFIX.size + length:]
        with self.assertRaisesRegex(FormationError, "JSON"):
            unpack_pair(raw, rehash(raw, self.policy))

    def test_dimensions_rejected_before_array_materialization(self):
        for dims in ([True, 16, 4], [4, 10**12, 4], [4, 0, 4]):
            raw = rewrite(self.raw, lambda h: h["source"].update(dimensions=dims))
            with patch("numpy.frombuffer", side_effect=AssertionError("must not allocate")):
                with self.assertRaises(FormationError):
                    unpack_pair(raw, rehash(raw, self.policy))

    def test_invalid_probes_and_provenance(self):
        for patcher in (lambda h: h.update(probes=[]), lambda h: h.update(probes=[[True] * 4]),
                        lambda h: h.update(generated_origin="observed"),
                        lambda h: h.update(source_provenance={"kind": "unknown"})):
            raw = rewrite(self.raw, patcher)
            with self.assertRaises(FormationError):
                unpack_pair(raw, rehash(raw, self.policy))

    def test_rehashed_certificate_is_checked_after_decode(self):
        raw = rewrite(self.raw, lambda h: h["certificate"]["parent_index"].__setitem__(0, 1))
        with self.assertRaisesRegex(FormationError, "incoming"):
            verify_capsule(raw, rehash(raw, self.policy))

    def test_corrupted_generated_model_rejected_even_with_all_hashes_rebound(self):
        bad = replace(self.child, down_weight=self.child.down_weight.copy())
        bad.down_weight[0, 0] += 0.25
        def change(h):
            h["generated"] = bad.descriptor()
            h["certificate"]["generated_digest"] = bad.descriptor()["digest"]
        # Source 592 bytes; generated incoming tensors then outgoing matrix.
        source_size = sum(getattr(self.source, k).nbytes for k in ("up_weight", "up_bias", "down_weight", "down_bias"))
        offset = source_size + bad.up_weight.nbytes + bad.up_bias.nbytes
        raw = rewrite(self.raw, change, lambda p: p[:offset] + bad.down_weight.astype("<f4").tobytes() + p[offset + bad.down_weight.nbytes:])
        policy = {**rehash(raw, self.policy), "generated_digest": bad.descriptor()["digest"]}
        with self.assertRaisesRegex(FormationError, "conservation"):
            verify_capsule(raw, policy)


class ChunkTests(unittest.TestCase):
    def setUp(self):
        source = procedural_block(4, 16, 4)
        child, certificate = widen(source, 24)
        self.raw, self.policy = pack_pair(source, child, certificate, {"kind": "procedural"}, [[0, 1, 2, 3]])
        self.message = {"request_id": "req", "kind": "chunk", "index": 0,
                        "data": base64.b64encode(self.raw).decode()}

    def test_complete_chunk_assembly_and_no_repeat(self):
        assembly = Assembly(self.policy, "req")
        assembly.accept(1, self.message)
        assembly.accept(2, {"request_id": "req", "kind": "verify"})
        self.assertEqual(assembly.report["status"], "verified")
        with self.assertRaises(FormationError):
            assembly.accept(3, self.message)

    def test_wrong_request_order_size_or_encoding(self):
        for changes in ({"request_id": "other"}, {"index": 1}, {"index": True},
                        {"data": "!"}, {"data": ""}, {"data": "a" * (2 * CHUNK)}):
            with self.subTest(changes=list(changes)):
                with self.assertRaises(FormationError):
                    Assembly(self.policy, "req").accept(1, {**self.message, **changes})

    def test_partial_transfer_never_becomes_verified(self):
        assembly = Assembly(self.policy, "req")
        with self.assertRaisesRegex(FormationError, "incomplete"):
            assembly.accept(1, {"request_id": "req", "kind": "verify"})
        self.assertIsNone(assembly.report)


if __name__ == "__main__":
    unittest.main()
