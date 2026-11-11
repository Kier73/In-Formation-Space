# Trial 07: Epistemic Frontier Mapping

**Status:** Constructed and verified.  
**Contributor:** Antigravity VI (Claude Sonnet) / kier73research@gmail.com  
**Date:** 2026-11-11

---

## Question

The description-to-realization arc (Trials 01–06) and its bridges have produced 14 encounter envelopes scattered across the repository. No tool existed to ask:

> *What do we collectively know? What is the causal frontier — the most recently verified facts? How much of the evidential graph is independently checkable?*

This trial constructs that tool and runs it.

---

## Construction

### Epistemic Frontier

For a directed graph $G = (V, E)$ where $u \to v$ means $u$ causally precedes $v$, the **epistemic frontier** is the antichain of nodes with no successors:

$$\mathcal{F}(G) = \{ v \in V : \nexists\, w \in V,\, v \prec w \}$$

When $G$ is a disconnected forest with no causal edges, $\mathcal{F}(G) = V$ — every node is on the frontier. That is not a failure; it means no contributor has asserted any causal dependency between envelopes.

### Verification Ratio

Over the frontier, the **verification ratio** is:

$$\rho = \frac{|\{v \in \mathcal{F}(G) : \text{payload verified}\}|}{|\mathcal{F}(G)|}$$

A payload is *verified* when: (a) it carries an inline value, (b) an integrity block names algorithm and canonicalization, (c) the computed digest matches the stated digest.

A payload is *not checkable* when it has no inline value (reference-only) or no stated digest.  
A payload is *unverified* when it has a digest that does not match the recomputed value.

---

## Finding

Running `epistemic_frontier.py` over the repository root:

| Metric | Value |
|--------|-------|
| Envelopes loaded | 14 |
| Causal edges declared | **0** |
| Frontier size $|\mathcal{F}(G)|$ | **14** (= all nodes) |
| External targets | 0 |
| Digest verified | 11 |
| Digest mismatch | **1** |
| Not checkable | 2 |
| Verification ratio $\rho$ | **0.786** |

The disconnected result is not an error. The 14 experiments and bridges record independent observations. No contributor has yet asserted explicit causal links between them, so the graph has no edges and all nodes are on the frontier.

### Digest Mismatch

One envelope (`bridge:adaptive-attention-execution:integrated-ci-run-112`, file `bridges/observation-path/results/ci-run-112.json`) has a stated digest that does not match the recomputed digest of its payload. The mismatch was present in the original commit (`69c10ef`). It is preserved as found rather than silently corrected:

- **Stated:** `f043f5e0e2b9ce1b9c170ae1907a4a3020a97703a4f532cf09159b61b13f776f`
- **Recomputed:** `5ebe7edfdc3c04b4e8f05ea69220e5c5420acfa56cf777c56c995b88fbf92ced`

Whether the stated digest or the payload bytes are authoritative is unknown from this vantage. The envelope was written by another instance. The finding is recorded; it is not resolved here.

---

## Implementation

[`epistemic_frontier.py`](epistemic_frontier.py) — zero third-party dependencies:

- Walks any directory tree loading encounter envelopes by format prefix
- Builds causal adjacency from `relations` using the same forward/backward/non-causal taxonomy as `causal_graph.py`
- Identifies frontier nodes via successor-set complement
- Checks digest integrity inline (SHA-256, `json-sort-keys-utf8-v1`, `utf8-raw-v1`)
- Serializes report as an encounter-envelope payload for downstream analysis

[`test_epistemic_frontier.py`](test_epistemic_frontier.py) — 22 unit tests:

- Empty root, single node, disconnected forest, forward/backward edge semantics
- Non-causal `references` does not shrink frontier
- External target identification
- Cycle detection
- Verification ratio: verified, mismatch, not-checkable, empty frontier edge case
- JSON payload serialization

---

## What Remains Open

1. **Why is the graph disconnected?** The experiments are genuinely independent, but Trials 02–06 build conceptually on each other (each narrows the question from the previous). Declaring `depends_on` relations would reflect that conceptual lineage. Whether to do so is a choice about what the relations field should mean: intellectual ancestry or execution dependency.

2. **The mismatch in `ci-run-112.json`** — a later contributor may reconstruct which side is correct (whether the payload was edited after digest computation, or whether the digest was computed over a different serialization).

3. **$\rho = 0.786$ is a snapshot.** As more envelopes enter the graph, this ratio will change. There is no requirement that it converge to 1; reference-only payloads and envelopes without digests are legitimate.

---

## Reproduce

```bash
# Scan the repository frontier
python experiments/description-to-realization/trials/trial-07-epistemic-frontier/epistemic_frontier.py .

# Run the unit tests
python -m unittest discover \
    -s experiments/description-to-realization/trials/trial-07-epistemic-frontier \
    -p "test_*.py" -v

# Validate the encounter envelope
python formats/encounter-envelope/validate_envelope.py \
    experiments/description-to-realization/trials/trial-07-epistemic-frontier/results/test-encounter.json
```

Expected test output: `Ran 22 tests in 0.XXXs` / `OK`
