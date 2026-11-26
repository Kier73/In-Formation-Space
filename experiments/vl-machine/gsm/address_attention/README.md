# GSM-003 — 24-bit address-space softmax

**Scope:** A constructive, trainable attention family over a virtual address product. The law is an exact real-arithmetic identity for the declared factorized key/value population, not a compression or equivalence theorem for arbitrary pretrained Transformer histories. Float64 implementations are compared within tolerances. No actual loopback sockets, E-CPU machines, external network, pretrained model or bare-metal execution is used.

## Address and Ground

Use four radix-64 digits (six bits each), corresponding to the 24-bit address universe explored by E-CPU's head index. For a=(a_0,...,a_3), define the key and value by

    K(a) = sum_j K_j[a_j]
    V(a) = sum_j V_j[a_j] + product_j P_j[a_j]   (componentwise)

Each factor table is retained. A query uses conventional scaled exponential softmax over all admitted addresses. For a Cartesian rectangle R = I_0 x ... x I_3:

    s_j(i) = q dot K_j[i] / sqrt(d_k)
    Z_j = sum_{i in I_j} exp(s_j(i))
    Z_R = product_j Z_j
    w_j(i) = exp(s_j(i))/Z_j
    E_R[V] = sum_j E_{w_j}[V_j] + product_j E_{w_j}[P_j]

This follows by distributivity: exp(sum s_j)=product exp(s_j), hence the normalized address distribution in the rectangle is a product distribution. The expectation formula applies to the additive and componentwise separable product terms. In a disjoint union of rectangles and singleton overrides, combine their expectations using normalized rectangle masses. Log-sum-exp avoids direct exponentiation of the total mass.

A causal prefix [0,T) is covered by disjoint Cartesian boxes, without realizing all addresses. Split around private address overrides and evaluate their replacement K/V independently; no subtraction of nearly equal masses. For a complete unpatched product, a query computes only L*R base scores and O(L*R*d_v) reductions after the dot products, not R^L individual scores. Arbitrary prefixes and exceptions add box and axis-slice work; the prototype caches shared slice summaries per query. Dense exceptions can erase the benefit. The reported base scores do not count summary or exception arithmetic. Numerical stability is tested at large finite scores, not guaranteed for arbitrary inputs near floating overflow. The Ground is a trusted local description with a content fingerprint, not a cryptographic admission or immutable host authority.

## Executed results

Python 3.13.5, NumPy 2.3.5, PyTorch 2.10.0+cpu, Linux x86-64, single BLAS thread. Five unit tests pass: exhaustive coverage of all intervals in a 27-address space, 42 patched/prefix/high-score comparisons, malformed query/override cases, independent uniform full-address expectation, and forward/gradient checks with four prefixes.

Single query across 16 sparse overrides; median of 11 Ground queries versus one streaming independent dense enumeration (chunks of 262144):

| Addresses | Ground ms | Dense ms | Max absolute error | Factor + override payload bytes |
|---:|---:|---:|---:|---:|
| 4,096 | 1.296 | 3.359 | 2.22e-15 | 5,696 |
| 65,536 | 1.748 | 46.272 | 3.66e-15 | 9,792 |
| 1,048,576 | 1.958 | 235.752 | 2.50e-15 | 17,984 |
| 16,777,216 | 2.156 | 3033.494 | 2.86e-15 | 34,368 |

Full space: 256 base scores, 104 boxes, 135 cached axis summaries, 16 override scores. A hypothetical fully materialized float64 K/V array at d_k=8,d_v=4 is 1,610,612,736 bytes. Payload excludes Python objects, query state, metadata, training and optimizer allocations. Dense reference streams rather than retaining this entire array. This is a compact generated population, not lossless compression of arbitrary data.

A stronger baseline in prefix_control.py caches axis logits but still enumerates all addresses. One local run:

| Prefix | Ground ms | Axis-cached enumeration ms | Max absolute error |
|---:|---:|---:|---:|
| 1 | 0.209 | 0.106 | 0 |
| 65,537 | 0.173 | 33.645 | 4.88e-15 |
| 12,345,678 | 2.811 | 1587.905 | 4.00e-15 |
| 16,777,216 | 2.837 | 2038.764 | 3.33e-15 |

Both controls include evaluation of the generated population; neither is an optimized dense Transformer implementation. Times are local illustrative results, not universal speed ratios. The single-coordinate case favors direct evaluation.

## Trainable head

trainable.py implements the same unpatched family with autograd, including irregular causal prefixes shared by the query batch. For 24 AdamW steps with 16 queries, alternating prefix sizes 1,127,1023,4096, independent dense materialization agrees with the compact forward route: maximum output discrepancy 6.01e-13, gradient discrepancy 9.76e-15, parameter trajectory discrepancy 3.80e-12. Tests compare derivatives with respect to queries and all factor tables. The separate full 24-bit learning run trains 4096 factor parameters for 100 updates on 64 queries, evaluates on 64 held-out queries, and reduces MSE 0.0229105657 -> 0.0000186325 (119.287 ms local training loop). The teacher belongs to the same family and is evaluated with the factorized function. This proves feasibility of training the constructed architecture, not recovery of arbitrary trained attention, learned factor discovery or general semantic capability. Overrides are supported in NumPy inference, not this differentiable implementation.

## Relationships

Studied (not imported) E-CPU main 8bba31aa0ad3d8f906babfdd83bf89221c704802: examples/fab_127/benchmark_head_index.py, mailcpu/attention.py, docs/FAB_020_VERIFIED_HEAD_ATTENTION.md. Use the 24-bit coordinate and metadata-first realization concept; the existing allocator's resource attention is not neural softmax. Studied VGI main 39a169b21513ffaaee85e40826c706c07a47215b: virtual_ground_interpreter/vgi/typed_operator_navigation.py (typed demand and unmaterialized chain). Existing IFS experiments/attention_ground_sufficiency solve a different sufficient-state problem for a finite-field affine kernel; this experiment retains exponential normalization. Source-qualified algebraic factorization, candidate search, and independent identity checking suggest how to discover further families. No private source content is included.

## Next

1. Introduce a learned address assignment, test factorized versus nonfactorized held-out tensors and independently measure reconstruction/attention error. Include irreducible random data and exact residual/override paths; do not force a Ground.
2. Add interaction terms on selected pairs of digits. Explore contraction order or variable elimination over a factor graph, where computational complexity depends on interaction structure rather than the number of virtual addresses. Count factor discovery and qualification separately.
3. Separate causal sequence position from virtual address. Implement revision-scoped append/update and sparse independent state, then source-bound E-CPU page/head admission and VGI verification. A 24-bit coordinate does not imply physical resources or 16 million independent trained states.
4. Train actual sequence models with the new head, compare quality and compute with dense and efficient attention at matched budgets. Derive error contracts before attempting pretrained KV transformation.

Reproduce:
    OPENBLAS_NUM_THREADS=1 python -m unittest -v
    OPENBLAS_NUM_THREADS=1 python address_attention.py --output report.json
    OPENBLAS_NUM_THREADS=1 python prefix_control.py --output prefix_report.json
    OPENBLAS_NUM_THREADS=1 python trainable.py --output training.json

Local report digests and result summary are retained in recipe.json. Timings and serialized floats are not CI identity gates. Independent CI pending.
