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
    CalibrationRangeError,
    ClockCalibrationError,
    InfeasibleCalibrationError,
    build_interval_affine_calibration,
    build_interval_demonstration,
    compare_two_sided_cross_clock_intervals,
    digest,
    map_source_interval_bounds,
    validate_interval_calibration,
)


def interval_anchor(
    anchor_id,
    source_lower,
    source_upper,
    target_lower,
    target_upper,
    *,
    basis="shared_trigger",
):
    witness_ref = f"capture://{anchor_id}"
    return {
        "anchor_id": anchor_id,
        "source_lower": source_lower,
        "source_upper": source_upper,
        "target_lower": target_lower,
        "target_upper": target_upper,
        "correlation_basis": basis,
        "witness_ref": witness_ref,
        "witness_sha256": digest({
            "anchor_id": anchor_id,
            "source": [source_lower, source_upper],
            "target": [target_lower, target_upper],
        }),
    }


def two_sided_calibration(anchors=None, **kwargs):
    return build_interval_affine_calibration(
        calibration_id="two-sided-test",
        source_clock_id="controller:C:segment-4",
        target_clock_id="sensor:S:segment-2",
        source_unit="tick",
        target_unit="tick",
        anchors=anchors or [
            interval_anchor("a", 0, 1, 100.0, 100.5),
            interval_anchor("b", 99, 101, 299.0, 301.0),
            interval_anchor("c", 199, 201, 499.0, 501.0),
        ],
        **kwargs,
    )


class TwoSidedAnchorConstructionTests(unittest.TestCase):
    def test_builds_and_reconstructs_interval_anchor_calibration(self):
        item = two_sided_calibration()
        self.assertEqual(item["format"], "in-formation.clock-calibration/0.2")
        self.assertEqual(
            item["anchor_semantics"],
            "mapped_source_interval_must_intersect_target_interval",
        )
        self.assertGreater(item["scale_bounds"]["lower"], 0)
        self.assertGreaterEqual(len(item["feasible_region"]), 1)
        self.assertEqual(validate_interval_calibration(item), item)

    def test_every_feasible_vertex_overlaps_each_mapped_anchor_interval(self):
        item = two_sided_calibration()
        for vertex in item["feasible_region"]:
            for anchor in item["anchors"]:
                mapped_lower = (
                    vertex["scale"] * anchor["source_lower"] + vertex["offset"]
                )
                mapped_upper = (
                    vertex["scale"] * anchor["source_upper"] + vertex["offset"]
                )
                self.assertLessEqual(mapped_lower, anchor["target_upper"] + 1e-8)
                self.assertGreaterEqual(mapped_upper + 1e-8, anchor["target_lower"])

    def test_anchor_permutation_is_deterministic(self):
        anchors = [
            interval_anchor("a", 0, 1, 100.0, 100.5),
            interval_anchor("b", 99, 101, 299.0, 301.0),
            interval_anchor("c", 199, 201, 499.0, 501.0),
        ]
        self.assertEqual(
            two_sided_calibration(anchors=anchors),
            two_sided_calibration(anchors=list(reversed(anchors))),
        )

    def test_exact_point_intervals_recover_unique_affine_map(self):
        item = two_sided_calibration(anchors=[
            interval_anchor("origin", 0, 0, 100.0, 100.0),
            interval_anchor("later", 100, 100, 300.0, 300.0),
        ])
        self.assertEqual(len(item["feasible_region"]), 1)
        self.assertAlmostEqual(item["feasible_region"][0]["scale"], 2.0)
        self.assertAlmostEqual(item["feasible_region"][0]["offset"], 100.0)

    def test_source_anchor_intervals_must_be_separated(self):
        with self.assertRaises(ClockCalibrationError):
            two_sided_calibration(anchors=[
                interval_anchor("a", 0, 10, 100.0, 110.0),
                interval_anchor("b", 5, 15, 105.0, 115.0),
            ])

    def test_nonmonotone_anchor_intervals_are_infeasible(self):
        with self.assertRaises(InfeasibleCalibrationError):
            two_sided_calibration(anchors=[
                interval_anchor("early", 0, 1, 200.0, 201.0),
                interval_anchor("late", 99, 100, 100.0, 101.0),
            ])

    def test_non_affine_exact_points_are_infeasible(self):
        with self.assertRaises(InfeasibleCalibrationError):
            two_sided_calibration(anchors=[
                interval_anchor("a", 0, 0, 100.0, 100.0),
                interval_anchor("b", 100, 100, 300.0, 300.0),
                interval_anchor("c", 200, 200, 450.0, 450.0),
            ])

    def test_invalid_source_or_target_anchor_interval_is_rejected(self):
        with self.assertRaises(ClockCalibrationError):
            two_sided_calibration(anchors=[
                interval_anchor("a", 10, 1, 100.0, 101.0),
                interval_anchor("b", 99, 100, 300.0, 301.0),
            ])
        with self.assertRaises(ClockCalibrationError):
            two_sided_calibration(anchors=[
                interval_anchor("a", 0, 1, 100.0, 99.0),
                interval_anchor("b", 99, 100, 300.0, 301.0),
            ])

    def test_duplicate_anchor_and_witness_ids_are_rejected(self):
        with self.assertRaises(ClockCalibrationError):
            two_sided_calibration(anchors=[
                interval_anchor("same", 0, 1, 100.0, 100.5),
                interval_anchor("same", 99, 101, 299.0, 301.0),
            ])
        first = interval_anchor("a", 0, 1, 100.0, 100.5)
        second = interval_anchor("b", 99, 101, 299.0, 301.0)
        second["witness_ref"] = first["witness_ref"]
        with self.assertRaises(ClockCalibrationError):
            two_sided_calibration(anchors=[first, second])


class TwoSidedMappingTests(unittest.TestCase):
    def test_maps_a_source_event_interval_over_feasible_set(self):
        item = two_sided_calibration()
        mapped = map_source_interval_bounds(
            item,
            source_clock_id="controller:C:segment-4",
            source_lower=49,
            source_upper=51,
            source_unit="tick",
        )
        self.assertLess(mapped["target_lower"], mapped["target_upper"])
        self.assertEqual(mapped["source_lower"], 49)
        self.assertEqual(mapped["source_upper"], 51)
        self.assertEqual(
            mapped["interpretation"],
            "two_sided_feasible_set_envelope_not_probability_or_confidence_interval",
        )

    def test_mapping_rejects_source_clock_segment_or_unit_mismatch(self):
        item = two_sided_calibration()
        with self.assertRaises(ClockCalibrationError):
            map_source_interval_bounds(
                item,
                source_clock_id="controller:C:segment-5",
                source_lower=49,
                source_upper=51,
                source_unit="tick",
            )
        with self.assertRaises(ClockCalibrationError):
            map_source_interval_bounds(
                item,
                source_clock_id="controller:C:segment-4",
                source_lower=49,
                source_upper=51,
                source_unit="millisecond",
            )

    def test_mapping_refuses_reversed_or_extrapolated_source_interval(self):
        item = two_sided_calibration()
        with self.assertRaises(ClockCalibrationError):
            map_source_interval_bounds(
                item,
                source_clock_id="controller:C:segment-4",
                source_lower=51,
                source_upper=49,
                source_unit="tick",
            )
        with self.assertRaises(CalibrationRangeError):
            map_source_interval_bounds(
                item,
                source_clock_id="controller:C:segment-4",
                source_lower=-1,
                source_upper=1,
                source_unit="tick",
            )
        with self.assertRaises(CalibrationRangeError):
            map_source_interval_bounds(
                item,
                source_clock_id="controller:C:segment-4",
                source_lower=200,
                source_upper=202,
                source_unit="tick",
            )

    def test_disjoint_two_sided_event_intervals_prove_before(self):
        report = build_interval_demonstration()
        result = report["comparisons"]["strictly_ordered"]
        self.assertEqual(result["relation"], "before")
        self.assertLess(
            result["mapped_source_interval"]["upper"],
            result["target_event_interval"]["lower"],
        )

    def test_overlapping_two_sided_event_intervals_remain_unresolved(self):
        report = build_interval_demonstration()
        result = report["comparisons"]["overlapping_uncertainty"]
        self.assertEqual(result["relation"], "overlap_unresolved")
        self.assertLessEqual(
            result["mapped_source_interval"]["lower"],
            result["target_event_interval"]["upper"],
        )

    def test_comparison_rejects_wrong_target_clock_and_unit(self):
        item = two_sided_calibration()
        args = dict(
            source_event_id="source",
            source_clock_id="controller:C:segment-4",
            source_lower=49,
            source_upper=51,
            source_unit="tick",
            target_event_id="target",
            target_lower=400,
            target_upper=401,
        )
        with self.assertRaises(ClockCalibrationError):
            compare_two_sided_cross_clock_intervals(
                item, target_clock_id="sensor:S:wrong", target_unit="tick", **args
            )
        with self.assertRaises(ClockCalibrationError):
            compare_two_sided_cross_clock_intervals(
                item, target_clock_id="sensor:S:segment-2", target_unit="nanosecond", **args
            )

    def test_comparison_rejects_same_event_identity(self):
        item = two_sided_calibration()
        with self.assertRaises(ClockCalibrationError):
            compare_two_sided_cross_clock_intervals(
                item,
                source_event_id="same",
                source_clock_id="controller:C:segment-4",
                source_lower=49,
                source_upper=51,
                source_unit="tick",
                target_event_id="same",
                target_clock_id="sensor:S:segment-2",
                target_lower=400,
                target_upper=401,
                target_unit="tick",
            )


class TwoSidedIntegrityTests(unittest.TestCase):
    def test_modified_feasible_region_is_detected(self):
        item = two_sided_calibration()
        altered = copy.deepcopy(item)
        altered["feasible_region"][0]["offset"] += 100
        core = {key: value for key, value in altered.items() if key != "calibration_digest"}
        altered["calibration_digest"] = digest(core)
        with self.assertRaises(ClockCalibrationError):
            validate_interval_calibration(altered)

    def test_interval_schema_accepts_calibration(self):
        if jsonschema is None:
            self.skipTest("jsonschema is optional")
        schema = json.loads(
            Path(__file__).with_name("clock-calibration-0.2.schema.json").read_text(
                encoding="utf-8"
            )
        )
        jsonschema.validate(instance=two_sided_calibration(), schema=schema)


if __name__ == "__main__":
    unittest.main()
