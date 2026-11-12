import copy
import json
import unittest
from pathlib import Path

try:
    import jsonschema
except ImportError:  # pragma: no cover
    jsonschema = None

from clock_calibration import (
    BASIS_VALUES,
    ClockCalibrationError,
    CalibrationRangeError,
    InfeasibleCalibrationError,
    build_affine_calibration,
    build_demonstration,
    compare_cross_clock_intervals,
    digest,
    map_source_interval,
    validate_calibration,
)


def anchor(
    anchor_id,
    source,
    lower,
    upper,
    *,
    basis="shared_trigger",
    witness=None,
):
    witness = witness or f"capture://{anchor_id}"
    return {
        "anchor_id": anchor_id,
        "source_coordinate": source,
        "target_lower": lower,
        "target_upper": upper,
        "correlation_basis": basis,
        "witness_ref": witness,
        "witness_sha256": digest({"witness": witness, "anchor": anchor_id}),
    }


def calibration(anchors=None, **kwargs):
    return build_affine_calibration(
        calibration_id="test-calibration",
        source_clock_id="controller:C",
        target_clock_id="sensor:S",
        source_unit="tick",
        target_unit="tick",
        anchors=anchors or [
            anchor("a", 0, 100.0, 100.4),
            anchor("b", 100, 300.0, 300.6),
            anchor("c", 200, 500.0, 500.5),
        ],
        **kwargs,
    )


class CalibrationConstructionTests(unittest.TestCase):
    def test_builds_positive_affine_feasible_region(self):
        item = calibration()
        self.assertEqual(item["format"], "in-formation.clock-calibration/0.1")
        self.assertGreaterEqual(item["scale_bounds"]["lower"], item["minimum_scale"])
        self.assertGreater(item["scale_bounds"]["upper"], 0)
        self.assertLessEqual(item["validity_source_min"], 0)
        self.assertGreaterEqual(item["validity_source_max"], 200)
        self.assertGreaterEqual(len(item["feasible_region"]), 1)
        self.assertEqual(validate_calibration(item), item)

    def test_anchor_permutation_produces_identical_calibration(self):
        anchors = [
            anchor("a", 0, 100.0, 100.4),
            anchor("b", 100, 300.0, 300.6),
            anchor("c", 200, 500.0, 500.5),
        ]
        first = calibration(anchors=anchors)
        second = calibration(anchors=list(reversed(anchors)))
        self.assertEqual(first, second)

    def test_anchor_intervals_are_all_satisfied_by_every_feasible_vertex(self):
        item = calibration()
        for vertex in item["feasible_region"]:
            for entry in item["anchors"]:
                mapped = vertex["scale"] * entry["source_coordinate"] + vertex["offset"]
                self.assertGreaterEqual(mapped + 1e-8, entry["target_lower"])
                self.assertLessEqual(mapped - 1e-8, entry["target_upper"])

    def test_inconsistent_nonmonotone_anchor_pair_is_rejected(self):
        anchors = [
            anchor("early", 0, 20.0, 20.1),
            anchor("late", 100, 10.0, 10.1),
        ]
        with self.assertRaises(InfeasibleCalibrationError):
            calibration(anchors=anchors)

    def test_anchors_must_span_two_source_coordinates(self):
        anchors = [
            anchor("a", 10, 20.0, 20.1),
            anchor("b", 10, 20.2, 20.3),
        ]
        with self.assertRaises(ClockCalibrationError):
            calibration(anchors=anchors)

    def test_anchor_ids_and_witness_refs_must_be_unique(self):
        duplicate_id = [
            anchor("same", 0, 1.0, 1.1),
            anchor("same", 100, 2.0, 2.1),
        ]
        with self.assertRaises(ClockCalibrationError):
            calibration(anchors=duplicate_id)

        duplicate_witness = [
            anchor("a", 0, 1.0, 1.1, witness="capture://same"),
            anchor("b", 100, 2.0, 2.1, witness="capture://same"),
        ]
        with self.assertRaises(ClockCalibrationError):
            calibration(anchors=duplicate_witness)

    def test_unknown_correlation_basis_is_rejected(self):
        with self.assertRaises(ClockCalibrationError):
            calibration(anchors=[
                anchor("a", 0, 100, 100.2, basis="similarity_match"),
                anchor("b", 100, 300, 300.2),
            ])

    def test_source_and_target_clock_ids_must_differ(self):
        with self.assertRaises(ClockCalibrationError):
            build_affine_calibration(
                calibration_id="invalid",
                source_clock_id="same",
                target_clock_id="same",
                source_unit="tick",
                target_unit="tick",
                anchors=[anchor("a", 0, 1, 1.1), anchor("b", 1, 2, 2.1)],
            )

    def test_validity_range_cannot_extrapolate_beyond_anchor_span(self):
        with self.assertRaises(ClockCalibrationError):
            calibration(validity_source_min=0, validity_source_max=201)

    def test_calibration_rejects_nonpositive_minimum_scale(self):
        with self.assertRaises(ClockCalibrationError):
            calibration(minimum_scale=0)


class CalibrationMappingTests(unittest.TestCase):
    def test_mapping_returns_envelope_over_every_admissible_mapping(self):
        item = calibration()
        result = map_source_interval(item, 50)
        self.assertLessEqual(result["target_lower"], result["target_upper"])
        self.assertEqual(result["source_coordinate"], 50)
        self.assertEqual(result["interpretation"], "feasible_set_envelope_not_probability_or_confidence_interval")

        mapped_vertices = [
            vertex["scale"] * 50 + vertex["offset"]
            for vertex in item["feasible_region"]
        ]
        self.assertAlmostEqual(result["target_lower"], min(mapped_vertices))
        self.assertAlmostEqual(result["target_upper"], max(mapped_vertices))

    def test_mapping_refuses_extrapolation(self):
        item = calibration()
        with self.assertRaises(CalibrationRangeError):
            map_source_interval(item, -1)
        with self.assertRaises(CalibrationRangeError):
            map_source_interval(item, 201)

    def test_disjoint_mapped_and_target_intervals_prove_before(self):
        report = build_demonstration()
        comparison = report["comparisons"]["strictly_ordered"]
        self.assertEqual(comparison["relation"], "before")
        self.assertLess(
            comparison["mapped_source_interval"]["upper"],
            comparison["target_event_interval"]["lower"],
        )

    def test_overlapping_intervals_remain_unresolved(self):
        report = build_demonstration()
        comparison = report["comparisons"]["overlapping_uncertainty"]
        self.assertEqual(comparison["relation"], "overlap_unresolved")
        self.assertLessEqual(
            comparison["mapped_source_interval"]["lower"],
            comparison["target_event_interval"]["upper"],
        )

    def test_reverse_direction_proves_after_when_source_envelope_is_later(self):
        item = calibration()
        result = compare_cross_clock_intervals(
            item,
            source_event_id="controller-late",
            source_coordinate=150,
            target_event_id="sensor-early",
            target_lower=200,
            target_upper=201,
        )
        self.assertEqual(result["relation"], "after")

    def test_touching_intervals_remain_unresolved(self):
        item = calibration()
        mapped = map_source_interval(item, 50)
        result = compare_cross_clock_intervals(
            item,
            source_event_id="source",
            source_coordinate=50,
            target_event_id="target",
            target_lower=mapped["target_upper"],
            target_upper=mapped["target_upper"] + 0.01,
        )
        self.assertEqual(result["relation"], "overlap_unresolved")

    def test_target_interval_must_be_well_formed(self):
        item = calibration()
        with self.assertRaises(ClockCalibrationError):
            compare_cross_clock_intervals(
                item,
                source_event_id="a",
                source_coordinate=10,
                target_event_id="b",
                target_lower=10,
                target_upper=9,
            )

    def test_event_ids_must_differ(self):
        item = calibration()
        with self.assertRaises(ClockCalibrationError):
            compare_cross_clock_intervals(
                item,
                source_event_id="same",
                source_coordinate=10,
                target_event_id="same",
                target_lower=1,
                target_upper=2,
            )


class CalibrationIntegrityTests(unittest.TestCase):
    def test_calibration_digest_and_feasible_region_are_reconstructed(self):
        item = calibration()
        changed = copy.deepcopy(item)
        changed["feasible_region"][0]["offset"] += 10
        core = {key: value for key, value in changed.items() if key != "calibration_digest"}
        changed["calibration_digest"] = digest(core)
        with self.assertRaises(ClockCalibrationError):
            validate_calibration(changed)

    def test_anchor_witness_digest_must_be_sha256(self):
        anchors = [
            anchor("a", 0, 100, 100.1),
            anchor("b", 100, 300, 300.1),
        ]
        anchors[0]["witness_sha256"] = "not-a-digest"
        with self.assertRaises(ClockCalibrationError):
            calibration(anchors=anchors)

    def test_schema_accepts_feasible_calibration(self):
        if jsonschema is None:
            self.skipTest("jsonschema is optional")
        schema = json.loads(
            (Path(__file__).with_name("clock-calibration.schema.json")).read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(instance=calibration(), schema=schema)

    def test_example_keeps_calibration_and_comparison_boundaries_explicit(self):
        report = build_demonstration()
        self.assertIn("calibration_digest", report["calibration"])
        self.assertTrue(all(
            "authenticated" in item or "probability" in item or "causation" in item
            for item in report["boundaries"]
        ))


if __name__ == "__main__":
    unittest.main()
