# AKS-001 — Attention as a navigable sufficient-state Ground

**Question:** Can a neural attention observer retain an exact, fixed-size computational Ground for arbitrary observed prefix length, rather than re-evaluating or replaying a growing token KV history on every new query?

**Answer for the *specified* Ground:** yes. For the affine kernel `K(q,k) = 1 + q·k` over the finite prime field `F_p`, every prefix has a sufficient state of size `O((d_k+1)(d_v+1))`, independent of the prefix length. A requested query observation uses only that state. This is a finite, exact instance of the known kernel/linear-attention associativity used in [Katharopoulos et al., ICML 2020](https://proceedings.mlr.press/v119/katharopoulos20a.html). **It is not an exact softmax Transformer, a new mathematical discovery, a recovered actual Qwen KV cache, or physical-path computation.**

## Ground, observer, and navigation

For observed causal prefix `(k_i,v_i)` with `k_i in F_p^d_k`, `v_i in F_p^d_v`, let `f(x)=(1,x_1,...,x_d_k)` and retain:

```
S_T = Σ_{i≤T} f(k_i) ⊗ v_i     shape (d_k+1) × d_v
z_T = Σ_{i≤T} f(k_i)           shape (d_k+1)
```

The next observed token is admitted by `S_(T+1) = S_T + f(k_(T+1)) ⊗ v_(T+1)` and `z_(T+1) = z_T + f(k_(T+1))`. The query observes

```
numerator(q)   = f(q)ᵀ S_T
mass(q)        = f(q)ᵀ z_T
raw(q)         = numerator(q)
normalized(q)  = numerator(q) / mass(q)   only when mass(q) != 0 in F_p
```

Distributivity proves this equals an explicit sum of per-token affine-kernel weights over **every** query and observed prefix in the declared field. A query requires `O(d_k*d_v)` field arithmetic, irrespective of `T`. Each *new* token requires `O(d_k*d_v)` arithmetic to update the state: the model does not claim zero computational cost or an ability to recover unobserved information. Independent verifier replay still costs `O(T*d_k*d_v)` and needs the original evidence if it is to re-establish the state from scratch.

`PrefixGround` retains the exact Ground fingerprint, the prefix index, the fixed-size `S,z`, and a SHA-256 hash-chain head for the admitted token observations. `TokenEvidence` binds the Ground, prefix index, previous digest, exact key and value. The head fingerprint includes the committed state and lineage, so two observationally equivalent summaries need not be mistaken for identical sources. Receiver-owned `expected_head` must be supplied to independently verify a query; a fully rehashed fake history is refused when its head differs from that trusted pin. Hashes alone are **not** host authentication, and this experiment adds no new Hypervisor, admission authority or remote transport.

## Necessary refusal: conventional softmax cannot use this Ground unchanged

Consider three real scalar keys `k=(0,1,2)` and two value histories `v_A=(2,2,2)` and `v_B=(3,0,3)`. Both yield identical prefix length, `Σk`, `Σv`, and `Σkv`; therefore they have **identical `S,z` under the affine feature map** and return the same affine-kernel observations for all queries. Yet at `q=1`, ordinary exponential softmax attention gives `2` for A and a different result for B. Thus equality of this sufficient state **cannot** authorize an exact softmax observation. Even a matching digest on a claimed observation cannot establish a law the Ground never admitted. Any softmax approximation requires a separately declared feature map, error contract and evidence; see [Performers (ICLR 2021)](https://research.google/pubs/rethinking-attention-with-performers/) for an example of approximate softmax attention using a different mathematical construction.

## Verification performed

From this directory, with Python 3.11+ and **standard library only**:

```bash
python -m unittest discover -s . -p 'test_attention_ground.py' -v
```

The six executable tests include: a 113-token, two-channel prefix with direct independent per-token oracle and receiver-pinned receipts; 2,000 prefix updates with invariant state shape; zero-denominator refusal; malformed and nonprime Grounds; token reordering/deletion/substitution; total history rewrite with new digests but the old receiver-owned root; mismatched observations; the explicit softmax counterexample; and exhaustive verification of all 625 two-token scalar histories in `F_5` at five query coordinates (raw and normalized when defined).

The exhaustive check covers the declared **small test domain**; the general equality follows from algebra rather than finite enumeration. Local passing tests do not establish hosted CI success. No actual pretrained parameters, tokenization, attention logits, or E-CPU operator invocation are involved in this experiment.

## Relationships and proposed next gate

- **E-CPU main:** its Ground, ObserverContract, Structural Memory and NavigableComputationDAG should own semantics, identities, dependencies and acceptance if the idea is operationalized. Do not instantiate a second runtime in this research experiment.
- **VGI main:** its typed exact matrix navigation and independent proof/evidence distinction can encode the transition and the requested query factorization; the finite algebra can be made a typed proof obligation rather than trusted from this Python implementation.
- **In-Formation-Space:** `tensor_cut_realization` and `semantic_neural_compilation` show independent numerical and semantic verification methods. AKS-001 tests a separate question: whether **retaining a Ground state** can replace repeatedly realizing all previous token pair contributions for a *known* kernel.
- **E-CPU-Virtual-Processor:** draft VP-004 navigates a token-coordinate Ground and runs a real sparse MoE feed-forward sublayer, but no persistent, verified attention/KV continuation yet. This is a candidate *alternative Ground design* for models whose attention actually uses a compatible kernel, not an assertion that Qwen3 softmax can be substituted.

**Next meaningful experiment:** attach AKS-001's state transition and query witness to E-CPU's existing operator/Hypervisor/DAG chain, retain the source-root pin through existing recovery lineage across a hard-killed receiver, then let VGI independently verify the exact finite-field kernel identity. Measure retained bytes, update cost, query cost, and re-verification cost separately from ordinary softmax reference inference. Attempting the same compression on a softmax model must refuse without a new, independently verified equivalence or approximation contract.

### Sources inspected

- E-CPU main `6fd416facdb2aefd6fc7d66a06b014e3d31b5a52` — `mailcpu/ground_native_realization.py`, `mailcpu/neural_graph_bridge.py`, `mailcpu/recovery_lineage.py`.
- VGI main `e6e1900782aeede18a4de9046511bbba234dbc6e` — `virtual_ground_interpreter/vgi/typed_operator_navigation.py`.
- In-Formation-Space main `c9716242725be65937fda1dd7b6cb778ca1def91` — `experiments/tensor_cut_realization/`, `experiments/semantic_neural_compilation/`.
- E-CPU-Virtual-Processor VP-004 draft `61781f011be8c6aef29e1cb2fed2f09d73c49177` — `docs/VP-004.md`.
