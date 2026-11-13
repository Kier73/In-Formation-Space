#!/usr/bin/env python3
"""Exact burst-loss retention models for an in-transit k-of-n word.

Two distinct Gilbert-Elliott structures are modeled:

* per_packet: every packet has its own independent good/bad Markov state.
  Losses are temporally correlated within a packet, but different packets have
  independent state paths. At a fixed horizon the survivor count is binomial.
* shared_channel: all packets share one good/bad channel state per
  circulation. Packet losses are conditionally independent given that shared
  state, but the common environment correlates losses across packets and time.

Within a circulation, packets are exposed to the current state first; the
Markov state transitions only after that circulation's losses. Lost packets
are absorbing. There is no repair, reordering, retransmission, or readout cost.

This is a finite-state probability model, not a hardware or network
measurement. See README.md for assumptions and interpretation limits.
"""
from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

MAX_SLOTS = 512
DEFAULT_SCAN_ROUNDS = 1000
SAMPLE_ROUNDS = (1, 2, 5, 10, 20, 50, 100, 250, 500, 1000)
MODELS = ("per_packet", "shared_channel")


def _probability(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a finite probability")
    try:
        number = float(value)
    except (OverflowError, TypeError, ValueError) as error:
        raise ValueError(f"{label} must be a finite probability") from error
    if not math.isfinite(number) or not 0.0 <= number <= 1.0:
        raise ValueError(f"{label} must be a finite probability in [0, 1]")
    return number


def _validate(
    slots: int,
    required: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    max_rounds: int,
) -> Tuple[float, float, float, float, float]:
    if not isinstance(slots, int) or isinstance(slots, bool) or not 1 <= slots <= MAX_SLOTS:
        raise ValueError(f"slots must be an integer in [1, {MAX_SLOTS}]")
    if not isinstance(required, int) or isinstance(required, bool) or not 1 <= required <= slots:
        raise ValueError("required must be an integer satisfying 1 <= required <= slots")
    if not isinstance(max_rounds, int) or isinstance(max_rounds, bool) or max_rounds < 1:
        raise ValueError("max_rounds must be a positive integer")
    p_good = _probability(good_loss_probability, "good_loss_probability")
    p_bad = _probability(bad_loss_probability, "bad_loss_probability")
    alpha = _probability(good_to_bad_probability, "good_to_bad_probability")
    beta = _probability(bad_to_good_probability, "bad_to_good_probability")
    initial_bad = _probability(initial_bad_probability, "initial_bad_probability")
    if p_good > p_bad:
        raise ValueError("good_loss_probability must not exceed bad_loss_probability")
    return p_good, p_bad, alpha, beta, initial_bad


def _binomial_probability_vector(trials: int, probability: float) -> Tuple[float, ...]:
    """Return the binomial PMF using log probabilities and normalization."""
    if probability <= 0.0:
        return (1.0,) + (0.0,) * trials
    if probability >= 1.0:
        return (0.0,) * trials + (1.0,)
    log_p = math.log(probability)
    log_q = math.log1p(-probability)
    values = []
    for successes in range(trials + 1):
        log_value = (
            math.lgamma(trials + 1)
            - math.lgamma(successes + 1)
            - math.lgamma(trials - successes + 1)
            + successes * log_p
            + (trials - successes) * log_q
        )
        values.append(math.exp(log_value))
    total = math.fsum(values)
    if total == 0.0:
        raise ArithmeticError("binomial probability vector underflowed completely")
    return tuple(value / total for value in values)


def binomial_tail_probability(slots: int, required: int, survival_probability: float) -> float:
    """Return P(Binomial(slots, survival_probability) >= required)."""
    if not isinstance(slots, int) or isinstance(slots, bool) or slots < 1:
        raise ValueError("slots must be a positive integer")
    if not isinstance(required, int) or isinstance(required, bool) or not 1 <= required <= slots:
        raise ValueError("required must satisfy 1 <= required <= slots")
    survival = _probability(survival_probability, "survival_probability")
    if survival <= 0.0:
        return 0.0
    if survival >= 1.0:
        return 1.0
    log_s = math.log(survival)
    log_l = math.log1p(-survival)

    def log_pmf(count: int) -> float:
        return (
            math.lgamma(slots + 1)
            - math.lgamma(count + 1)
            - math.lgamma(slots - count + 1)
            + count * log_s
            + (slots - count) * log_l
        )

    if required <= slots // 2:
        lower = math.fsum(math.exp(log_pmf(count)) for count in range(required))
        if lower < 1.0:
            return min(1.0, max(0.0, 1.0 - lower))
    upper = math.fsum(math.exp(log_pmf(count)) for count in range(required, slots + 1))
    return min(1.0, max(0.0, upper))


def per_packet_retention_curve(
    slots: int,
    required: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    max_rounds: int,
) -> List[float]:
    """Exact retention for independent per-packet Gilbert-Elliott chains.

    mass_good and mass_bad are joint probabilities that one packet is
    still alive and currently in each channel state. The state at the start of
    a round controls that round's loss probability; surviving mass is then
    transitioned to the next state. Packet chains are independent, so the
    number alive at a fixed horizon is Binomial with the marginal survival
    probability computed here.
    """
    p_good, p_bad, alpha, beta, initial_bad = _validate(
        slots, required, good_loss_probability, bad_loss_probability,
        good_to_bad_probability, bad_to_good_probability, initial_bad_probability,
        max_rounds,
    )
    mass_good = 1.0 - initial_bad
    mass_bad = initial_bad
    curve = [1.0]
    survive_good = 1.0 - p_good
    survive_bad = 1.0 - p_bad
    for _ in range(max_rounds):
        after_good = mass_good * survive_good
        after_bad = mass_bad * survive_bad
        mass_good = after_good * (1.0 - alpha) + after_bad * beta
        mass_bad = after_good * alpha + after_bad * (1.0 - beta)
        one_packet_survival = min(1.0, max(0.0, math.fsum((mass_good, mass_bad))))
        curve.append(binomial_tail_probability(slots, required, one_packet_survival))
    return curve


def shared_channel_retention_curve(
    slots: int,
    required: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    max_rounds: int,
) -> List[float]:
    """Exact retention with one Markov channel state shared by every packet.

    Dynamic-programming state is (alive_packet_count, channel_state).
    Conditional on the current shared state, the remaining packets are
    thinned by its loss probability; only then does the shared channel state
    transition. Paths that fall below the recovery threshold are discarded,
    because lost packets cannot return without repair.
    """
    p_good, p_bad, alpha, beta, initial_bad = _validate(
        slots, required, good_loss_probability, bad_loss_probability,
        good_to_bad_probability, bad_to_good_probability, initial_bad_probability,
        max_rounds,
    )
    q_good = 1.0 - p_good
    q_bad = 1.0 - p_bad
    good_kernel = {
        alive: _binomial_probability_vector(alive, q_good)
        for alive in range(required, slots + 1)
    }
    bad_kernel = {
        alive: _binomial_probability_vector(alive, q_bad)
        for alive in range(required, slots + 1)
    }

    # Each array holds joint mass for surviving the complete prefix and
    # entering the next circulation with this many packets alive in a state.
    mass_good = [0.0] * (slots + 1)
    mass_bad = [0.0] * (slots + 1)
    mass_good[slots] = 1.0 - initial_bad
    mass_bad[slots] = initial_bad
    curve = [1.0]

    for _ in range(max_rounds):
        next_good = [0.0] * (slots + 1)
        next_bad = [0.0] * (slots + 1)
        for alive in range(required, slots + 1):
            good_mass = mass_good[alive]
            if good_mass:
                probabilities = good_kernel[alive]
                for remaining in range(required, alive + 1):
                    after_loss = good_mass * probabilities[remaining]
                    next_good[remaining] += after_loss * (1.0 - alpha)
                    next_bad[remaining] += after_loss * alpha
            bad_mass = mass_bad[alive]
            if bad_mass:
                probabilities = bad_kernel[alive]
                for remaining in range(required, alive + 1):
                    after_loss = bad_mass * probabilities[remaining]
                    next_good[remaining] += after_loss * beta
                    next_bad[remaining] += after_loss * (1.0 - beta)
        mass_good, mass_bad = next_good, next_bad
        retention = math.fsum(mass_good[required:]) + math.fsum(mass_bad[required:])
        curve.append(min(1.0, max(0.0, retention)))
    return curve


def iid_baseline_retention_curve(
    slots: int,
    required: int,
    average_loss_probability: float,
    max_rounds: int,
) -> List[float]:
    """IID-per-round comparison using the same stationary one-round loss rate."""
    p = _probability(average_loss_probability, "average_loss_probability")
    _validate(slots, required, p, p, 0.0, 0.0, 0.0, max_rounds)
    result = []
    for rounds in range(max_rounds + 1):
        q = 1.0 if rounds == 0 else (1.0 - p) ** rounds
        result.append(binomial_tail_probability(slots, required, q))
    return result


def _no_finite_half_life(
    model: str,
    slots: int,
    required: int,
    p_good: float,
    p_bad: float,
    alpha: float,
    beta: float,
    initial_bad: float,
) -> bool:
    """Detect an absorbing loss-free good state with limiting retention > 1/2.

    When good is loss-free and absorbing, a packet/block initially in bad may
    survive enough bad-state circulations to transition into the good state.
    This computes that eventual retained mass rather than counting only the
    probability of starting in good. A limit strictly above 1/2 guarantees
    that no finite circulation can cross the half-retention threshold.
    Exact equality is conservatively left to the finite-horizon/censor status.
    """
    if model not in MODELS:
        raise ValueError(f"unknown model: {model}")
    if p_good == 0.0 and p_bad == 0.0:
        return True
    if p_good != 0.0 or alpha != 0.0:
        return False

    initial_good = 1.0 - initial_bad
    if model == "per_packet":
        if beta == 0.0:
            bad_to_good_survival = 0.0
        else:
            q_bad = 1.0 - p_bad
            bad_to_good_survival = (
                q_bad * beta / (1.0 - q_bad * (1.0 - beta))
            )
        limiting_single_packet_survival = (
            initial_good + initial_bad * bad_to_good_survival
        )
        limiting_retention = binomial_tail_probability(
            slots, required, limiting_single_packet_survival
        )
        return limiting_retention > 0.5

    # In the shared-channel model, while the channel remains bad, the block
    # loses packets under one common state. Let f[m] be the probability that
    # a block with m live packets in B eventually reaches absorbing G with at
    # least 'required' packets. Condition on one bad-state thinning, then on
    # whether the channel transitions to G. The no-loss-and-stay-B term that
    # recurs to f[m] is moved to the left-hand side.
    if beta == 0.0:
        limiting_retention = initial_good
    else:
        q_bad = 1.0 - p_bad
        f = [0.0] * (slots + 1)
        for alive in range(required, slots + 1):
            probabilities = _binomial_probability_vector(alive, q_bad)
            no_loss_stay_bad = (1.0 - beta) * probabilities[alive]
            denominator = 1.0 - no_loss_stay_bad
            direct_success = beta * math.fsum(probabilities[required:])
            continuation = (1.0 - beta) * math.fsum(
                probabilities[remaining] * f[remaining]
                for remaining in range(required, alive)
            )
            f[alive] = (direct_success + continuation) / denominator
        limiting_retention = initial_good + initial_bad * f[slots]

    return limiting_retention > 0.5


def half_life_summary(
    curve: Sequence[float],
    *,
    no_finite_half_life: bool = False,
) -> Dict[str, Any]:
    """Return first integer crossing or an explicit no-crossing/censor status."""
    if no_finite_half_life:
        return {"status": "no_finite_half_life", "first_crossing_round": None}
    for rounds, probability in enumerate(curve[1:], start=1):
        if probability <= 0.5:
            return {"status": "crossed", "first_crossing_round": rounds}
    return {
        "status": "not_reached_within_horizon",
        "first_crossing_round": None,
        "censored_at_round": len(curve) - 1,
    }


def simulate_retention(
    model: str,
    slots: int,
    required: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    rounds: int,
    trials: int,
    seed: int = 0,
) -> float:
    """Seeded simulation of one of the exact models, for implementation checks."""
    if model not in MODELS:
        raise ValueError(f"model must be one of {MODELS}")
    if not isinstance(rounds, int) or isinstance(rounds, bool) or rounds < 0:
        raise ValueError("rounds must be a non-negative integer")
    p_good, p_bad, alpha, beta, initial_bad = _validate(
        slots, required, good_loss_probability, bad_loss_probability,
        good_to_bad_probability, bad_to_good_probability, initial_bad_probability,
        max(1, rounds),
    )
    if not isinstance(trials, int) or isinstance(trials, bool) or trials < 1:
        raise ValueError("trials must be a positive integer")
    rng = random.Random(seed)
    successes = 0
    for _ in range(trials):
        alive = [True] * slots
        if model == "per_packet":
            states = [rng.random() < initial_bad for _ in range(slots)]
            for _round in range(rounds):
                for index, state_bad in enumerate(states):
                    if not alive[index]:
                        continue
                    loss = p_bad if state_bad else p_good
                    if rng.random() < loss:
                        alive[index] = False
                        continue
                    if state_bad:
                        states[index] = not (rng.random() < beta)
                    else:
                        states[index] = rng.random() < alpha
        else:
            state_bad = rng.random() < initial_bad
            for _round in range(rounds):
                loss = p_bad if state_bad else p_good
                for index in range(slots):
                    if alive[index] and rng.random() < loss:
                        alive[index] = False
                if state_bad:
                    state_bad = not (rng.random() < beta)
                else:
                    state_bad = rng.random() < alpha
        if sum(alive) >= required:
            successes += 1
    return successes / trials


def summarize_scenario(
    *,
    name: str,
    slots: int,
    required: int,
    good_loss_probability: float,
    bad_loss_probability: float,
    good_to_bad_probability: float,
    bad_to_good_probability: float,
    initial_bad_probability: float,
    max_rounds: int = DEFAULT_SCAN_ROUNDS,
    simulation_trials: Optional[int] = None,
    simulation_seed: int = 0,
) -> Dict[str, Any]:
    p_good, p_bad, alpha, beta, initial_bad = _validate(
        slots, required, good_loss_probability, bad_loss_probability,
        good_to_bad_probability, bad_to_good_probability, initial_bad_probability,
        max_rounds,
    )
    average_loss = (1.0 - initial_bad) * p_good + initial_bad * p_bad
    curves = {
        "iid_average": iid_baseline_retention_curve(slots, required, average_loss, max_rounds),
        "per_packet": per_packet_retention_curve(
            slots, required, p_good, p_bad, alpha, beta, initial_bad, max_rounds
        ),
        "shared_channel": shared_channel_retention_curve(
            slots, required, p_good, p_bad, alpha, beta, initial_bad, max_rounds
        ),
    }
    result_models: Dict[str, Any] = {}
    for index, model in enumerate(("iid_average",) + MODELS):
        no_finite = False
        if model != "iid_average":
            no_finite = _no_finite_half_life(
                model, slots, required, p_good, p_bad, alpha, beta, initial_bad
            )
        half_life = half_life_summary(curves[model], no_finite_half_life=no_finite)
        samples = {
            str(round_number): curves[model][round_number]
            for round_number in SAMPLE_ROUNDS
            if round_number <= max_rounds
        }
        model_result: Dict[str, Any] = {
            **half_life,
            "retention_at_rounds": samples,
        }
        if simulation_trials is not None:
            horizon = half_life.get("first_crossing_round") or max_rounds
            if model == "iid_average":
                # The baseline is simulated by an independent per-round loss
                # model, which is the p_good == p_bad special case.
                sim = simulate_retention(
                    "per_packet", slots, required, average_loss, average_loss,
                    0.0, 0.0, 0.0, horizon, simulation_trials, simulation_seed + index,
                )
            else:
                sim = simulate_retention(
                    model, slots, required, p_good, p_bad, alpha, beta,
                    initial_bad, horizon, simulation_trials, simulation_seed + index,
                )
            model_result["simulation"] = {
                "round": horizon,
                "trials": simulation_trials,
                "seed": simulation_seed + index,
                "retention_estimate": sim,
                "exact_retention": curves[model][horizon],
            }
        result_models[model] = model_result

    return {
        "name": name,
        "parameters": {
            "slots": slots,
            "required": required,
            "good_loss_probability": p_good,
            "bad_loss_probability": p_bad,
            "good_to_bad_probability": alpha,
            "bad_to_good_probability": beta,
            "initial_bad_probability": initial_bad,
            "stationary_bad_probability": (
                alpha / (alpha + beta) if alpha + beta > 0.0 else None
            ),
            "marginal_first_round_loss_probability": average_loss,
            "max_rounds": max_rounds,
        },
        "models": result_models,
        "interpretation": [
            "The iid_average model uses the same marginal first-round loss probability but removes temporal and cross-packet state correlation.",
            "per_packet gives each packet an independent Markov channel state; losses are temporally correlated within a packet but packet states are independent.",
            "shared_channel gives all packets one common Markov state per circulation; conditional packet drops are independent given that state, but common-state variation correlates the block's losses.",
            "The state active at the start of a circulation controls losses in that circulation; the state transitions afterward.",
            "A first_crossing_round is the first integer circulation whose retention probability is <= 0.5; no fractional-round interpolation is used.",
            "not_reached_within_horizon is right-censored, not proof of an infinite half-life; no_finite_half_life is reserved for a detected loss-free absorbing-state case.",
            "The model has no repair, retransmission, channel authentication, readout cost, or measured physical link behavior.",
        ],
    }


DEFAULT_SCENARIOS = (
    {
        "name": "intact_block_stationary_bursts",
        "slots": 32, "required": 32,
        "good_loss_probability": 0.001, "bad_loss_probability": 0.35,
        "good_to_bad_probability": 0.025, "bad_to_good_probability": 0.20,
        "initial_bad_probability": 0.025 / (0.025 + 0.20),
    },
    {
        "name": "half_threshold_stationary_bursts",
        "slots": 64, "required": 32,
        "good_loss_probability": 0.001, "bad_loss_probability": 0.35,
        "good_to_bad_probability": 0.025, "bad_to_good_probability": 0.20,
        "initial_bad_probability": 0.025 / (0.025 + 0.20),
    },
    {
        "name": "replicated_word_stationary_bursts",
        "slots": 64, "required": 1,
        "good_loss_probability": 0.001, "bad_loss_probability": 0.35,
        "good_to_bad_probability": 0.025, "bad_to_good_probability": 0.20,
        "initial_bad_probability": 0.025 / (0.025 + 0.20),
    },
    {
        "name": "persistent_bad_state",
        "slots": 32, "required": 24,
        "good_loss_probability": 0.0005, "bad_loss_probability": 0.90,
        "good_to_bad_probability": 0.01, "bad_to_good_probability": 0.05,
        "initial_bad_probability": 0.01 / (0.01 + 0.05),
    },
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare exact k-of-n retention under iid and burst-correlated packet loss.")
    parser.add_argument("--scan", action="store_true", help="run the fixed burst-loss scenarios")
    parser.add_argument("--slots", type=int, default=32)
    parser.add_argument("--required", type=int, default=32)
    parser.add_argument("--good-loss", type=float, default=0.001)
    parser.add_argument("--bad-loss", type=float, default=0.35)
    parser.add_argument("--good-to-bad", type=float, default=0.025)
    parser.add_argument("--bad-to-good", type=float, default=0.20)
    parser.add_argument("--initial-bad", type=float, default=0.025 / (0.025 + 0.20))
    parser.add_argument("--max-rounds", type=int, default=DEFAULT_SCAN_ROUNDS)
    parser.add_argument("--simulate", action="store_true", help="add seeded Monte Carlo checks at each model's crossing or horizon")
    parser.add_argument("--trials", type=int, default=10000)
    parser.add_argument("--seed", type=int, default=20261112)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.scan:
            scenarios = [summarize_scenario(**item, max_rounds=args.max_rounds,
                                            simulation_trials=args.trials if args.simulate else None,
                                            simulation_seed=args.seed + index * 100)
                         for index, item in enumerate(DEFAULT_SCENARIOS)]
        else:
            scenarios = [summarize_scenario(
                name="custom",
                slots=args.slots,
                required=args.required,
                good_loss_probability=args.good_loss,
                bad_loss_probability=args.bad_loss,
                good_to_bad_probability=args.good_to_bad,
                bad_to_good_probability=args.bad_to_good,
                initial_bad_probability=args.initial_bad,
                max_rounds=args.max_rounds,
                simulation_trials=args.trials if args.simulate else None,
                simulation_seed=args.seed,
            )]
        if args.json:
            rendered = json.dumps(scenarios, indent=2, sort_keys=True, allow_nan=False)
        else:
            lines = ["scenario  model  half-life status  first crossing round"]
            for scenario in scenarios:
                for model, result in scenario["models"].items():
                    lines.append(
                        f"{scenario['name']}  {model}  {result['status']}  "
                        f"{result.get('first_crossing_round', 'n/a')}"
                    )
            rendered = "\n".join(lines)
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8", newline="\n")
            print(f"wrote {args.output}")
        else:
            print(rendered)
        return 0
    except (ArithmeticError, OSError, TypeError, ValueError) as error:
        parser.error(str(error))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
