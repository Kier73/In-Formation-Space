# MMG-002 / MMG-003 — Fusion grounds and ordered translation

Source: [OpenAI, The matrix multiplication exponent is nine fourths, November 24, 2026](https://github.com/openai/math/tree/main/preprints/The-matrix-multiplication-exponent-is-nine-fourths-November-24-2026), especially build/fermions.tex, fusion width lemma. All energy indices in scripts are doubled.

## Reproduce
Python 3.11+ with numpy and sympy. Run in this directory:
```sh
python mmg002_fusion.py 20
python mmg002_verify.py
python mmg002_integral.py
python mmg003_order.py > mmg003_results.json
```
The first three commands regenerate the MMG-002 receipt. The committed JSON files record completed local runs, not CI or distributed executions.

## MMG-002
For a basis of V_E and V_G, enumerate the rows of the fusion map to Hom(V_G,V_E) in increasing input energy. Eliminate modulo each prime and retain the first full-rank cutoff. The independently implemented Pfaffian checks the coefficient recursion. Integer HNF checks generation of the complete integer matrix-unit lattice for four configurations. 400 pairs, 2,000 finite-field span tests, 816,561 coefficients, 20,000 Pfaffian comparisons. All tested nonempty pairs span by the published bound; 399 improve strictly across all five fields. The (12,11) pair has dimension six and integral cutoff 15 against published cutoff 52. A single unimodular subset was not found there; field-specific invertible subsets are used in MMG-003.

## MMG-003: independent tensor factors as translation ground
For M_i with shape o_i x n_i, K = tensor_i M_i. For a general dense input tensor, realize K by acting on each axis exactly once, without constructing K. The actions commute because they affect different axes. On a current tensor of N coordinates, factor i costs N*c_i sparse multiplication terms, where c_i=nnz(M_i)/n_i and r_i=o_i/n_i; it changes N to N*r_i. Adjacent orders ij and ji differ by N*(c_i*(1-r_j)-c_j*(1-r_i)). Thus an exact minimum-term ordering is contractions first, then neutral factors, then expansions, each nonneutral class in ascending c_i/(1-r_i). All contractions before expansions also minimize peak logical coordinate count to max(input,output). This proof is for independent factors and the declared sparse term model, not arbitrary tensor networks or hardware timing. Addition counts are tracked separately; multiplication by a constant is counted as a term even if the constant is one.

Results: 30 small dense/roundtrip comparisons over 5 fields; 100 heterogeneous comparisons and 12,000 exhaustively compared orders; maximum worst/best term ratio 2720/29. For the 6-dimensional fusion basis over F_11, eight tensor factors realize all 1,679,616 coordinates; a flat dense transform would have 2,821,109,907,456 entries, of which 16,983,563,041 are nonzero. Factorwise execution charges 42,550,272 terms and 29,113,344 additions; 0.179 s forward, 0.196 s inverse in one local run, full exact roundtrip plus eight independently evaluated flat rows. Logical coordinate count does not measure peak allocated RAM. Dense baseline counts are calculated, not executed.

## Fabric continuation
Each axis exposes independent fibers. Partition on inactive coordinates, bind a receipt to source ground identity, field, axis, stage, fiber interval, input digest and output digest, verify disjoint complete coverage, then atomically commit the next stage. Repartition/transpose and charge actual data movement when the next active axis changes. A descriptor for a product of k independent grounds is O(k) factor references, but arbitrary dense inputs/outputs require materialization and communication proportional to their size. Measure operation spans with bridges/observation-path/operation_spans.py; the E-CPU DAG/admission and quorum-fenced rehome model is an integration target, not yet invoked here. Independent factors alone do not imply a new matrix-multiplication exponent. Next attack: discover exact nonseparable ground decompositions of T_n or a violated hypothesis in the lower-bound manuscript, and charge basis generation, arithmetic, verification, routing, and reconstruction.
