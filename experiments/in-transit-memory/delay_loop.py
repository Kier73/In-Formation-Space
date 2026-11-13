#!/usr/bin/env python3
"""Retention of a k-of-n word in a lossy delay loop.

The model is deliberately small:

- ``n`` packets occupy ``n`` independent slots in a circulating loop.
- One circulation takes ``period`` time units.
- Each packet independently survives a circulation with probability ``1 - p``.
- A logical word is recoverable while at least ``k`` of its ``n`` packets survive.
- There is no repair, refresh, duplication, correlated loss, or readout cost.

The exact retention probability after ``r`` circulations is therefore

    R(r) = P(Binomial(n, (1 - p)**r) >= k).

This is a probability model, not a hardware or network measurement. See
README.md for the assumptions and claim boundaries. Zero third-party
dependencies.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MAX_SLOTS = 512

# Scenarios used by ``--scan``. They contrast an intact block (k = n), a
# middle-threshold erasure code, and full replication (k = 1) at two loss
# rates, plus a high-loss case that exposes the small-p limit of the source
# half-life formula.
SCAN_SCENARIOS: Tuple[Tuple[int, int, float], ...] = (
    (64, 64, 0.01),
    (64, 32, 0.01),
    (64, 1, 0.01),
    (64, 64, 0.10),
    (64, 32, 0.10),
    (64, 1, 0.10),
    (8, 8, 0.50),
)


def _validate_parameters(slots: int, required: int, loss_probability: float) -> None:
    if not isinstance(slots, int) or isinstance(slots, bool) or slots < 1:
        raise ValueError("slots must be a positive integer")
    if slots > MAX_SLOTS:
        raise ValueError(f"slots must be <= {MAX_SLOTS}")
    if not isinstance(required, int) or isinstance(required, bool):
        raise ValueError("required must be an integer")
    if not 1 <= required <= slots:
        raise ValueError("required must satisfy 1 <= required <= slots")
    if isinstance(loss_probability, bool) or not isinstance(
        loss_probability, (int, float)
    ):
        raise ValueError("loss_probability must be a number")
    if not 0.0 <= float(loss_probability) <= 1.0:
        raise ValueError("loss_probability must be in [0, 1]")


def _validate_period(period: float) -> None:
    if isinstance(period, bool) or not isinstance(period, (int, float)):
        raise ValueError("period must be a number")
    if not float(period) > 0.0:
        raise ValueError("period must be positive")


def _binomial_tail_with_log(
    slots: int, required: int, survival: float
) -> Tuple[float, float]:
    """Return ``(P(X >= required), log P(X >= required))``.

    The shorter tail is summed to avoid losing a tiny complementary
    probability to floating-point rounding. For example, when ``required`` is
    small and survival is high, the upper tail is nearly 1; computing the
    lower tail and subtracting it from 1 preserves the log of the small
    failure probability, which is what a repair-epoch median needs.
    """
    if survival <= 0.0:
        return 0.0, float("-inf")
    if survival >= 1.0:
        return 1.0, 0.0

    log_s = math.log(survival)
    log_failure = math.log1p(-survival)

    def log_pmf(survived: int) -> float:
        log_coefficient = (
            math.lgamma(slots + 1)
            - math.lgamma(survived + 1)
            - math.lgamma(slots - survived + 1)
        )
        return (
            log_coefficient
            + survived * log_s
            + (slots - survived) * log_failure
        )

    if required <= slots // 2:
        # P(X >= required) = 1 - P(X <= required - 1).
        lower = 0.0
        for survived in range(0, required):
            lower += math.exp(log_pmf(survived))
        if lower <= 0.0:
            return 1.0, 0.0
        if lower < 1.0:
            return 1.0 - lower, math.log1p(-lower)
        # The complement is not resolvable; fall through to the upper tail.

    upper = 0.0
    for survived in range(required, slots + 1):
        upper += math.exp(log_pmf(survived))
    if upper <= 0.0:
        return 0.0, float("-inf")
    probability = min(1.0, upper)
    return probability, math.log(probability)


def _binomial_tail(slots: int, required: int, survival: float) -> float:
    """Return P(Binomial(slots, survival) >= required)."""
    probability, _ = _binomial_tail_with_log(slots, required, survival)
    return probability


def retention_probability(
    slots: int,
    required: int,
    loss_probability: float,
    rounds: float,
) -> float:
    """Exact probability that at least ``required`` packets survive.

    ``rounds`` may be fractional; the expression is the continuous
    interpolation used to define a half-life, not a claim that packets are
    inspected between circulations.
    """
    _validate_parameters(slots, required, loss_probability)
    if isinstance(rounds, bool) or not isinstance(rounds, (int, float)):
        raise ValueError("rounds must be a number")
    if rounds < 0.0:
        raise ValueError("rounds must be non-negative")
    if rounds == 0.0:
        return 1.0

    loss_probability = float(loss_probability)
    if loss_probability == 0.0:
        return 1.0
    if loss_probability == 1.0:
        return 0.0

    survival = (1.0 - loss_probability) ** rounds
    return _binomial_tail(slots, required, survival)


def half_life_rounds(
    slots: int,
    required: int,
    loss_probability: float,
    *,
    max_iterations: int = 200,
) -> Optional[float]:
    """Circulations until retention first reaches 1/2.

    Returns ``None`` when loss is zero. A loss probability of exactly 1 is
    rejected because retention jumps from 1 at zero rounds to 0 immediately
    afterwards, so a continuous half-life does not exist.
    """
    _validate_parameters(slots, required, loss_probability)
    loss_probability = float(loss_probability)
    if loss_probability == 0.0:
        return None
    if loss_probability == 1.0:
        raise ValueError(
            "half-life is undefined at loss_probability=1; retention is discontinuous"
        )

    low = 0.0
    high = 1.0
    while (
        retention_probability(slots, required, loss_probability, high) > 0.5
    ):
        high *= 2.0
        if high > 1.0e12:
            raise RuntimeError("half-life exceeded the search bound")

    for _ in range(max_iterations):
        middle = (low + high) / 2.0
        if (
            retention_probability(slots, required, loss_probability, middle)
            > 0.5
        ):
            low = middle
        else:
            high = middle
    return (low + high) / 2.0


def exact_half_life_time(
    slots: int,
    required: int,
    loss_probability: float,
    period: float = 1.0,
) -> Optional[float]:
    """Half-life in time units; ``None`` for zero loss."""
    _validate_period(period)
    rounds = half_life_rounds(slots, required, loss_probability)
    if rounds is None:
        return None
    return rounds * float(period)


def source_formula_half_life_time(
    slots: int,
    loss_probability: float,
    period: float = 1.0,
) -> float:
    """The source note's approximation: period * ln(2) / (slots * p).

    It is the first-order small-p approximation of intact-block retention
    (``required == slots``) with independent per-packet loss. It is not a
    general k-of-n formula, and it is not exact for large p.
    """
    if not isinstance(slots, int) or isinstance(slots, bool) or slots < 1:
        raise ValueError("slots must be a positive integer")
    _validate_period(period)
    if isinstance(loss_probability, bool) or not isinstance(
        loss_probability, (int, float)
    ):
        raise ValueError("loss_probability must be a number")
    loss_probability = float(loss_probability)
    if not 0.0 < loss_probability < 1.0:
        raise ValueError(
            "the source formula requires 0 < loss_probability < 1"
        )
    return float(period) * math.log(2.0) / (slots * loss_probability)


def simulate_retention(
    slots: int,
    required: int,
    loss_probability: float,
    rounds: float,
    trials: int,
    seed: int = 0,
) -> float:
    """Seeded Monte Carlo estimate of :func:`retention_probability`.

    Each trial samples the endpoint survival of every packet directly from
    ``(1 - p)**rounds``. That is equivalent to simulating every circulation
    independently, because the packet losses are independent.
    """
    _validate_parameters(slots, required, loss_probability)
    if isinstance(rounds, bool) or not isinstance(rounds, (int, float)):
        raise ValueError("rounds must be a number")
    if rounds < 0.0:
        raise ValueError("rounds must be non-negative")
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise ValueError("trials must be a positive integer")

    loss_probability = float(loss_probability)
    if rounds == 0.0 or loss_probability == 0.0:
        return 1.0
    if loss_probability == 1.0:
        return 0.0

    survival = (1.0 - loss_probability) ** rounds
    rng = random.Random(seed)
    successes = 0
    for _ in range(trials):
        alive = sum(1 for _ in range(slots) if rng.random() < survival)
        if alive >= required:
            successes += 1
    return successes / trials


def repair_survival_probability(
    slots: int,
    required: int,
    loss_probability: float,
    epoch_rounds: float,
    epochs: int,
) -> float:
    """Survival across repair epochs that restore all slots when possible.

    At the end of each epoch, if at least ``required`` packets survive, the
    word is decoded and all ``slots`` packets are rewritten. Otherwise the
    word is lost. Epochs are independent under the stated loss model.
    """
    _validate_parameters(slots, required, loss_probability)
    if isinstance(epoch_rounds, bool) or not isinstance(epoch_rounds, (int, float)):
        raise ValueError("epoch_rounds must be a number")
    if epoch_rounds < 0.0:
        raise ValueError("epoch_rounds must be non-negative")
    if not isinstance(epochs, int) or isinstance(epochs, bool) or epochs < 0:
        raise ValueError("epochs must be a non-negative integer")
    epoch_survival = retention_probability(
        slots, required, loss_probability, epoch_rounds
    )
    return epoch_survival ** epochs


def repair_median_epochs(
    slots: int,
    required: int,
    loss_probability: float,
    epoch_rounds: float,
) -> Optional[float]:
    """Continuous median number of repair epochs before the word is lost.

    The actual integer epoch at which survival first reaches 1/2 is this
    value rounded up. ``None`` means the per-epoch survival probability is 1.
    """
    _validate_parameters(slots, required, loss_probability)
    if isinstance(epoch_rounds, bool) or not isinstance(epoch_rounds, (int, float)):
        raise ValueError("epoch_rounds must be a number")
    if epoch_rounds < 0.0:
        raise ValueError("epoch_rounds must be non-negative")

    loss_probability = float(loss_probability)
    if loss_probability == 0.0:
        return None
    if loss_probability == 1.0:
        return 0.0

    survival = (1.0 - loss_probability) ** epoch_rounds
    _, log_epoch_survival = _binomial_tail_with_log(
        slots, required, survival
    )
    if log_epoch_survival >= 0.0:
        return None
    if log_epoch_survival == float("-inf"):
        return 0.0
    return math.log(0.5) / log_epoch_survival


def summarize(
    slots: int,
    required: int,
    loss_probability: float,
    period: float = 1.0,
    *,
    trials: Optional[int] = None,
    seed: int = 0,
) -> Dict[str, Any]:
    """Return a JSON-serializable summary for one parameter set."""
    _validate_parameters(slots, required, loss_probability)
    _validate_period(period)
    loss_probability = float(loss_probability)
    period = float(period)

    rounds = half_life_rounds(slots, required, loss_probability)
    exact_time = None if rounds is None else rounds * period
    formula_time: Optional[float] = None
    formula_ratio: Optional[float] = None
    if 0.0 < loss_probability < 1.0:
        formula_time = source_formula_half_life_time(
            slots, loss_probability, period
        )
        if exact_time is not None and exact_time > 0.0:
            formula_ratio = formula_time / exact_time

    result: Dict[str, Any] = {
        "slots": slots,
        "required": required,
        "loss_probability": loss_probability,
        "period": period,
        "exact_half_life_rounds": rounds,
        "exact_half_life_time": exact_time,
        "retention_at_half_life": (
            None
            if rounds is None
            else retention_probability(slots, required, loss_probability, rounds)
        ),
        "source_formula_applicable": required == slots,
        "source_formula_half_life_time": formula_time,
        "source_formula_ratio_to_exact": formula_ratio,
    }
    if trials is not None and rounds is not None:
        result["simulated_retention_at_half_life"] = simulate_retention(
            slots, required, loss_probability, rounds, trials, seed
        )
        result["simulation_trials"] = trials
        result["simulation_seed"] = seed
    return result


def _format_value(value: Optional[float], digits: int = 6) -> str:
    if value is None:
        return "n/a"
    return f"{value:.{digits}g}"


def format_table(rows: Sequence[Dict[str, Any]]) -> str:
    """Render summaries as a compact fixed-width table."""
    headers = (
        "slots",
        "k",
        "p",
        "exact r",
        "exact t",
        "formula t",
        "formula/exact",
        "R(r1/2)",
    )
    lines = [
        "  ".join(
            [
                f"{headers[0]:>5}",
                f"{headers[1]:>3}",
                f"{headers[2]:>5}",
                f"{headers[3]:>11}",
                f"{headers[4]:>11}",
                f"{headers[5]:>11}",
                f"{headers[6]:>15}",
                f"{headers[7]:>9}",
            ]
        ),
        "  ".join(
            [
                "-" * 5,
                "-" * 3,
                "-" * 5,
                "-" * 11,
                "-" * 11,
                "-" * 11,
                "-" * 15,
                "-" * 9,
            ]
        ),
    ]
    for row in rows:
        formula = row["source_formula_half_life_time"]
        formula_text = _format_value(formula)
        if not row["source_formula_applicable"]:
            formula_text += "*"
        lines.append(
            "  ".join(
                [
                    f"{row['slots']:>5}",
                    f"{row['required']:>3}",
                    f"{row['loss_probability']:>5g}",
                    f"{_format_value(row['exact_half_life_rounds']):>11}",
                    f"{_format_value(row['exact_half_life_time']):>11}",
                    f"{formula_text:>11}",
                    f"{_format_value(row['source_formula_ratio_to_exact']):>15}",
                    f"{_format_value(row['retention_at_half_life'], 5):>9}",
                ]
            )
        )
    return "\n".join(lines)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compute exact retention half-lives for a k-of-n word in a "
            "lossy circulating delay loop."
        )
    )
    parser.add_argument("--slots", type=int, default=64, help="packets per word")
    parser.add_argument(
        "--required",
        type=int,
        default=None,
        help="packets required for recovery (default: all slots)",
    )
    parser.add_argument(
        "--loss",
        type=float,
        default=0.01,
        help="independent loss probability per packet per circulation",
    )
    parser.add_argument(
        "--period",
        type=float,
        default=1.0,
        help="time units per circulation",
    )
    parser.add_argument(
        "--scan",
        action="store_true",
        help="run the fixed comparison scenarios",
    )
    parser.add_argument(
        "--simulate",
        action="store_true",
        help="add a seeded Monte Carlo estimate at the exact half-life",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=20000,
        help="Monte Carlo trials when --simulate is used",
    )
    parser.add_argument("--seed", type=int, default=0, help="Monte Carlo seed")
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON instead of a text table",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="write the output to this path as UTF-8 instead of stdout",
    )
    return parser


def render_output(rows: Sequence[Dict[str, Any]], as_json: bool) -> str:
    """Render summaries as JSON or as the explanatory text table."""
    if as_json:
        return json.dumps(rows, indent=2, sort_keys=True)
    lines = [
        format_table(rows),
        "",
        "exact r = circulations to retention 1/2; exact t = exact r * period.",
        (
            "formula t = period * ln(2) / (slots * p), the source note's "
            "small-p intact-block approximation."
        ),
        (
            "* the source formula is not a k-of-n formula; its value is shown "
            "only for comparison."
        ),
    ]
    return "\n".join(lines)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    trials = args.trials if args.simulate else None

    if args.scan:
        rows = [
            summarize(
                slots,
                required,
                loss,
                period=args.period,
                trials=trials,
                seed=args.seed,
            )
            for slots, required, loss in SCAN_SCENARIOS
        ]
    else:
        required = args.required if args.required is not None else args.slots
        rows = [
            summarize(
                args.slots,
                required,
                args.loss,
                period=args.period,
                trials=trials,
                seed=args.seed,
            )
        ]

    rendered = render_output(rows, args.json)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8", newline="\n")
        print(f"wrote {args.output}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
