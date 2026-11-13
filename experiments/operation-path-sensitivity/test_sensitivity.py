import copy
import hashlib
import itertools
import json
import unittest

from sensitivity import build_sensitivity_report, validate_sensitivity_report, OperationPathError
from operation_path_criticality import build_operation_path_trace
from test_operation_path_criticality import span


def evidence(weights, edges):
    nodes = []
    start = 0
    for i, weight in enumerate(weights):
        nodes.append(span(span_id=str(i), operation_id="work", start=start, end=start + weight))
        start += weight
    root = span(span_id="root", operation_id="root", start=0, end=start)
    trace = build_operation_path_trace(
        path_id="sensitivity", attempt_id="attempt-1", root_span_digest=root["span_digest"],
        operation_span_digests=[n["span_digest"] for n in nodes],
        must_complete_before=[{"predecessor_span_digest": nodes[a]["span_digest"],
                               "successor_span_digest": nodes[b]["span_digest"]} for a, b in edges],
    )
    return [root] + nodes, trace


def paths(node_count, edges):
    """Independent exhaustive oracle, not the production dynamic program."""
    outgoing = {n: [b for a, b in edges if a == n] for n in range(node_count)}
    roots = [n for n in range(node_count) if all(b != n for _, b in edges)]
    result = []

    def visit(prefix):
        if not outgoing[prefix[-1]]:
            result.append(prefix)
        for child in outgoing[prefix[-1]]:
            visit(prefix + [child])

    for root in roots:
        visit([root])
    return result


class SensitivityTests(unittest.TestCase):
    def test_tied_branches_require_joint_reduction(self):
        spans, trace = evidence([10, 10, 5], [(0, 2), (1, 2)])
        original = copy.deepcopy((spans, trace))
        reductions = {spans[1]["span_digest"]: 4, spans[2]["span_digest"]: 4}
        report = build_sensitivity_report(spans, trace=trace, reductions=reductions)
        rows = {r["span_id"]: r for r in report["nodes"]}
        self.assertEqual(report["critical_path_count"], 2)
        self.assertEqual(rows["0"]["full_removal_benefit_ns"], 0)
        self.assertEqual(rows["1"]["full_removal_benefit_ns"], 0)
        self.assertEqual(rows["2"]["full_removal_benefit_ns"], 5)
        self.assertTrue(rows["2"]["on_every_critical_path"])
        self.assertEqual(report["counterfactual_benefit_ns"], 4)
        self.assertEqual((spans, trace), original)
        self.assertEqual(validate_sensitivity_report(report, spans, trace=trace), report)

    def test_benefit_stops_when_competing_path_takes_over(self):
        spans, trace = evidence([10, 8, 5], [(0, 2), (1, 2)])
        report = build_sensitivity_report(spans, trace=trace, reductions={spans[1]["span_digest"]: 7})
        self.assertEqual(report["baseline_dependency_path_ns"], 15)
        self.assertEqual(report["counterfactual_dependency_path_ns"], 13)
        self.assertEqual(report["counterfactual_benefit_ns"], 2)

    def test_all_four_node_forward_dags_and_binary_durations(self):
        possible = list(itertools.combinations(range(4), 2))
        for mask in range(1 << len(possible)):
            edges = [edge for bit, edge in enumerate(possible) if mask & (1 << bit)]
            sequences = paths(4, edges)
            for weights in itertools.product((0, 1), repeat=4):
                with self.subTest(edges=edges, weights=weights):
                    spans, trace = evidence(weights, edges)
                    report = build_sensitivity_report(spans, trace=trace)
                    costs = [sum(weights[n] for n in p) for p in sequences]
                    longest = max(costs)
                    critical = [p for p, cost in zip(sequences, costs) if cost == longest]
                    self.assertEqual(report["baseline_dependency_path_ns"], longest)
                    self.assertEqual(report["critical_path_count"], len(critical))
                    for row in report["nodes"]:
                        n = int(row["span_id"])
                        through = max(cost for p, cost in zip(sequences, costs) if n in p)
                        critical_count = sum(n in p for p in critical)
                        shortened = max(sum(weights[k] for k in p if k != n) for p in sequences)
                        self.assertEqual(row["longest_path_through_ns"], through)
                        self.assertEqual(row["path_gap_ns"], longest - through)
                        self.assertEqual(row["critical_path_count_through"], critical_count)
                        self.assertEqual(row["on_every_critical_path"], critical_count == len(critical))
                        self.assertEqual(row["full_removal_benefit_ns"], longest - shortened)

    def test_input_order_does_not_choose_a_different_result(self):
        spans, trace = evidence([2, 2, 1], [(0, 2), (1, 2)])
        self.assertEqual(build_sensitivity_report(spans, trace=trace),
                         build_sensitivity_report(list(reversed(spans)), trace=trace))

    def test_invalid_reductions_are_rejected(self):
        spans, trace = evidence([2], [])
        digest = spans[1]["span_digest"]
        for value in [True, False, -1, 3, 1.0, "1", None]:
            with self.subTest(value=value), self.assertRaises(OperationPathError):
                build_sensitivity_report(spans, trace=trace, reductions={digest: value})
        for reductions in [[], {spans[0]["span_digest"]: 0}, {"unknown": 0}]:
            with self.assertRaises(OperationPathError):
                build_sensitivity_report(spans, trace=trace, reductions=reductions)

    def test_rehashed_forgery_is_rejected(self):
        spans, trace = evidence([1], [])
        for field, value in [("counterfactual_benefit_ns", 100), ("critical_path_count", True)]:
            report = build_sensitivity_report(spans, trace=trace)
            report[field] = value
            core = {k: v for k, v in report.items() if k != "report_digest"}
            report["report_digest"] = hashlib.sha256(json.dumps(core, sort_keys=True,
                separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
            with self.assertRaises(OperationPathError):
                validate_sensitivity_report(report, spans, trace=trace)

    def test_source_validation_is_not_bypassed(self):
        spans, trace = evidence([1], [])
        spans[1]["elapsed_ns"] = 0
        with self.assertRaises(ValueError):
            build_sensitivity_report(spans, trace=trace)


if __name__ == "__main__":
    unittest.main()
