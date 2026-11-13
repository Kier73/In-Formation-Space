"""Run RIV-006's exact persistent-context filtering counterexample."""
import json

from context_switching_evidence import build_report, validate_report


def sensor(name):
    return {
        "sensor_id": name,
        "p_signal_a_given_hypothesis_a_good": "9/10",
        "p_signal_a_given_hypothesis_b_good": "1/10",
        "p_signal_a_given_hypothesis_a_degraded": "1/2",
        "p_signal_a_given_hypothesis_b_degraded": "1/2",
    }


def main():
    report = build_report(
        prior_hypothesis_a="1/2",
        prior_context_good="1/2",
        context_transition={
            "p_good_next_given_good": "9/10",
            "p_good_next_given_degraded": "1/10",
        },
        sensors=tuple(sensor(f"sensor-{index}") for index in range(1, 5)),
    )
    validate_report(report)
    layer = next(
        item for item in report["joint_posterior_accumulator"]["layers"]
        if item["step"] == 2
    )
    witness = next(
        item for item in layer["separate_marginal_next_update_divergences"]
        if item["shared_posterior_hypothesis_a"] == {
            "numerator": 1, "denominator": 2
        }
    )
    print(json.dumps({
        "format": report["format"],
        "summary": report["summary"],
        "ab_ba_counterexample": witness,
        "content_digest": report["content_digest"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
