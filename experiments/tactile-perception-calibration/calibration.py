"""TPP-004: discover a transferable affine expression from paired observations.

The learner does not use the known foot-to-metre constant to fit the relation.
It uses exact rational feasible-interval inequalities and held-out probes.
Physical accuracy and independence of the original NOAA instruments remain unknown.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from fractions import Fraction as Q
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "tactile-perception-observations"))
from independent_replay import verify as verify_noaa
from noaa_bridge import live as live_noaa

SCHEMA="in-formation-space.tpp004.observer-relative-scale.v1"
EPS=Q(1,1000)
KNOWN_FOOT_TO_M=Q(381,1250)  # used ONLY in post-fit audit; not by fit or score


def rational(v):
    if not isinstance(v,Q):
        raise TypeError("exact fractions required")
    return f"{v.numerator}/{v.denominator}"


@dataclass(frozen=True)
class Relation:
    lower: Q
    upper: Q
    alpha: Q
    intercept: Q
    epsilon: Q
    origin_count: int

    def predict(self,x):
        return self.alpha*x+self.intercept

    def record(self):
        return {
            "alpha_min":rational(self.lower), "alpha_max":rational(self.upper),
            "selected_alpha":rational(self.alpha),
            "selected_intercept":rational(self.intercept),
            "tolerance_in_output_units":rational(self.epsilon),
            "fitted_pairs":self.origin_count,
            "reference_scale_inside_interval_posthoc":
                self.lower<=KNOWN_FOOT_TO_M<=self.upper,
            "claim":"feasible-linear-model-on-training-only",
        }


def fit(pairs,epsilon=EPS):
    """Infer ALL positive slopes permitting a common intercept within +/-epsilon.

    Exact constraints: y-eps <= a*x+b <= y+eps for every supplied pair.
    For each different-x pair i,j, elimination of b gives
    (dy-2eps)/dx <= a <= (dy+2eps)/dx. Intersection is sufficient because
    pairwise overlap of 1D intercept intervals implies global overlap.
    """
    if not isinstance(epsilon,Q) or epsilon<=0:
        raise ValueError("positive rational tolerance required")
    observations=list(pairs)
    if len(observations)<4:
        return None, "insufficient-training-observations"
    for x,y in observations:
        if not isinstance(x,Q) or not isinstance(y,Q):
            raise TypeError("only exact rational observations accepted")
    low=Q(0);high=None
    for i,(x,y) in enumerate(observations):
        for prior_x,prior_y in observations[:i]:
            dx=x-prior_x
            dy=y-prior_y
            if dx==0:
                if abs(dy)>2*epsilon:
                    return None,"inconsistent-equal-inputs"
                continue
            if dx<0:
                dx,dy=-dx,-dy
            bound_low=(dy-2*epsilon)/dx
            bound_high=(dy+2*epsilon)/dx
            low=max(low,bound_low)
            high=bound_high if high is None else min(high,bound_high)
            if high<low:
                return None,"contradictory-training-observations"
    if high is None:
        return None,"no-observed-input-variation"
    # Distinguish formal fit from a meaningful calibration when input span
    # is smaller than the observed output tolerance.
    if max(x for x,_ in observations)-min(x for x,_ in observations)<=epsilon:
        return None,"insufficient-input-variation"
    if high<low:
        return None,"contradictory-training-observations"
    alpha=(low+high)/2
    b_min=max(y-alpha*x-epsilon for x,y in observations)
    b_max=min(y-alpha*x+epsilon for x,y in observations)
    if b_min>b_max:
        raise AssertionError("pairwise interval elimination disagrees with intercepts")
    return Relation(low,high,alpha,(b_min+b_max)/2,epsilon,len(observations)),"fit"


def challenge(relation,pairs):
    """Pre-registered validation: no mutation of the fitted coefficients."""
    failures=[]
    max_residual=Q(0)
    for time,x,y in pairs:
        residual=abs(y-relation.predict(x))
        max_residual=max(max_residual,residual)
        if residual>relation.epsilon:
            failures.append((time,residual))
    return {
        "status":"falsified" if failures else "heldout-consistent",
        "tested":len(pairs),
        "violations":len(failures),
        "max_abs_residual":rational(max_residual),
        "first_counterexample_utc":failures[0][0] if failures else None,
        "first_counterexample_residual":rational(failures[0][1]) if failures else None,
    }


def _paired_observations(source):
    documents=source.get("observations")
    if not isinstance(documents,list) or len(documents)!=2:
        raise ValueError("expected exactly two physical-observation expressions")
    left,right=documents
    if left.get("status")!="observed" or right.get("status")!="observed":
        return None,"unavailable-or-invalid-observations"
    if any(left.get(k)!=right.get(k) for k in ("station","datum","time_zone","product")):
        return None,"incompatible-physical-reference"
    if (left.get("units"),right.get("units"))!=("m","ft"):
        return None,"incompatible-unit-expressions"
    data=[]
    for doc in documents:
        keyed={}
        for row in doc["observations"]:
            t=row["timestamp_utc"]
            if t in keyed:
                return None,"duplicate-timestamp"
            keyed[t]=row
        data.append(keyed)
    pairs=[];skipped=0
    for t in sorted(data[0].keys() & data[1].keys()):
        m,e=data[0][t],data[1][t]
        if m["value"] is None or e["value"] is None:
            skipped+=1;continue
        if m["provider_quality"]!=e["provider_quality"]:
            return None,"provider-quality-mismatch"
        pairs.append((t,Q(e["value"]),Q(m["value"])))
    return (pairs,skipped),"paired"


def infer(report,stride=100):
    """Replay bytes first, then learn without known conversion factor.

    Entire unselected timestamps remain held out. The number of timestamps
    sets the observation schedule, but none of their values enters the fit.
    """
    if type(stride) is not int or stride<2:
        raise ValueError("stride must be an integer >=2")
    try:
        verified=verify_noaa(report)
    except (ValueError,TypeError,KeyError,ArithmeticError,OverflowError) as exc:
        return {"schema":SCHEMA,"status":"invalid-source-evidence",
                "reason":type(exc).__name__}
    if verified["status"]!="unit-expression-consistent":
        return {"schema":SCHEMA,"status":"undetermined",
                "reason":"source-replay-or-translation-not-consistent",
                "replay_status":verified["status"]}
    result,reason=_paired_observations(report)
    if result is None:
        return {"schema":SCHEMA,"status":"undetermined","reason":reason}
    pairs,skipped=result
    selected=[(x,y) for i,(_,x,y) in enumerate(pairs) if i%stride==0]
    heldout=[(t,x,y) for i,(t,x,y) in enumerate(pairs) if i%stride]
    relation,fit_status=fit(selected)
    if relation is None:
        return {"schema":SCHEMA,"status":"undetermined","reason":fit_status,
                "paired_timestamps":len(pairs),"training_pairs":len(selected)}
    outcome=challenge(relation,heldout)
    metric,english=report["observations"]
    return {
        "schema":SCHEMA,"status":outcome["status"],
        "evidence_scope":"one-provider-cross-unit-not-independent-physical-sensing",
        "source_sha256":{"metric":metric["raw_sha256"],
                         "english":english["raw_sha256"]},
        "source_station":metric["station"],"datum":metric["datum"],
        "quality":"provider-preliminary-or-verified-retained-per-row",
        "paired_timestamps":len(pairs),"skipped_unpaired_values":skipped,
        "training_schedule":"every-%d-th-matched-timestamp"%stride,
        "training_pairs":len(selected),"heldout_pairs":len(heldout),
        "model":relation.record(), "heldout":outcome,
    }


def experiment():
    source=live_noaa()
    return {"schema":SCHEMA,"read_only_source":source,"inference":infer(source)}


def replay(path):
    data=json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("schema")!=SCHEMA:
        raise ValueError("not a TPP-004 encounter")
    actual=infer(data["read_only_source"])
    if actual!=data["inference"]:
        raise ValueError("retained inference disagrees with complete independent replay")
    return {"scope":"replayed-archived-remote-bytes-not-instrument-certified",
            "status":actual["status"],
            "heldout_pairs":actual.get("heldout_pairs")}


if __name__=="__main__":
    parser=argparse.ArgumentParser()
    modes=parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--live",action="store_true")
    modes.add_argument("--replay")
    args=parser.parse_args()
    if args.live:
        print(json.dumps(experiment(),sort_keys=True,indent=2))
    else:
        print(json.dumps(replay(args.replay),sort_keys=True,indent=2))
