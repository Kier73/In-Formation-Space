# OTG-001 — Obstruction-directed quadratic observation Grounds

**Question.** Can a failed observation representation produce the missing mathematical coordinate, rather than merely trigger another candidate search? Can that newly formed representation pay for its own construction on subsequent intentions?

**Status:** executable exact finite-field research. The two deterministic campaigns were executed in a JavaScript isolate, including a reload of the committed source; hosted Node execution is registered separately. This is a new local experiment, not an imported runtime or a general complexity theorem.

## Public research lineage

- [TDL-002](../../reports/TRANSLATION_DISCOVERY_LOG_002.md) (IFS `ccf7dfb88a52c458ee9dd00e26ffbaecf5b2af9c`): exact additional row-space information for a changed intention.
- [CIG-001–034A](../pnp-ground-navigation/README.md) (same IFS revision): different intentions over one source, source-derived observation languages, sufficiency and constructive sections.
- [GCI-003](../cross-ground-continuity/gci003/README.md) (same IFS revision): a target-specific answer can require less than the entire transition law.
- [NCR-007](https://github.com/Kier73/Navigable-Compute/blob/34f540dbaef9de2b495f85a64f817817979c5ca6/docs/NCR-007.md): exact nonlinear observer-feature closure; linear feature dimension and realized quotient size are different.
- [VLD mathematical foundations](https://github.com/Kier73/Virtual-Layer-Dynamics/blob/afe54804bc15ea14b1c51766757edef3aac96817/docs/MATHEMATICAL_FOUNDATIONS.md): observer-relative quotient, law identifiability and inclusive navigation cost.

These are studied public precursors, not imported code. OTG-001 uses a standalone exact quadratic ANF source and a new checker. It constructs a target-specific linear measurement language, not a future-action closure.

## Mathematical contract

Input is the whole binary cube X=F2^n (1<=n<=128), a supplied expanded quadratic algebraic normal form

    f(x) = c + sum_i a_i x_i + sum_(i<j) b_ij x_i x_j,

and optional independent existing linear observations Q0. Arithmetic in this section is in F2. An intention is to reconstruct f(x) for every x using a linear observation q(x)=Qx whose rows extend Q0. A representation is sufficient iff f(x+d)=f(x) for all x and all d in ker Q. Neither the factorization generating the source nor an answer oracle is supplied to the constructor.

Define B to be the alternating polar matrix with B_ij=B_ji=b_ij and zero diagonal. Then

    f(x+d)+f(x) = x^T B d + f(d)+f(0).

Consequently every sufficient Q satisfies row(B) subset row(Q): if d lies in ker Q, the derivative must be identically zero in x, which implies Bd=0. This is a necessary algebraic condition, not a heuristic.

Let U=row([Q0;B]), K=U^perp, r=dim U. On K, h(d)=f(d)+f(0) is linear: for d,e in K, their polar pairing vanishes, so h(d+e)=h(d)+h(e). If h is identically zero, U suffices. Otherwise extend this linear functional from K to the whole cube and append its row t. Then ker Q=K intersect ker t, and the derivative vanishes there. Every sufficient Q extending Q0 needs at least one more independent row in this latter case, because U itself has a witness d in K with h(d)=1.

**Exact minimum total row rank in this contract:**

    rank Q_min = rank([Q0;B]) + indicator(h restricted to K is nonzero).

The number of additional measurement bits is rank Q_min-rank Q0. This is a statement about **unrestricted exact linear measurements** on the full cube, not arbitrary nonlinear observations (the bit f(x) itself would suffice), restricted physical sensors, an optimal decoder cost, or all possible algorithms.

## Failure constructs the new coordinate

1. Start from Q0. For each source polar row B_i outside the current row span, solve for d with Qd=0 and B_i d=1. Choose x=0 or e_i so the derivative is nonzero. The pair x,x+d agrees on every currently observed coordinate but disagrees on the intended output. Append B_i, a row that every sufficient linear language must contain in its span.
2. Once all polar rows are admitted, inspect a basis of the remaining kernel K. Nonzero h(d) is a constant-derivative obstruction. Construct a single extension row t by its values on free-coordinate basis vectors, eliminating the entire remaining linear obstruction, not just the exhibited pair.
3. Construct a linear right section S of Q and evaluate the coefficients of g(z)=f(Sz). Then f=g o Q, since x+SQx lies in ker Q.
4. Independently check the original source, row independence, every obstruction and its prefix, polar rank lower bound, optional radical lower bound, and the entire symbolic identity g(Qx)=f(x) by expanding Boolean ANF monomials. No call to the producer's elimination, section, or discovery routine occurs in this verifier. It uses high pivots instead of low pivots for rank. It trusts neither a digest nor reported producer expenditure.

The producer returns in-memory BigInt row masks, events and decoder. Source and old observations are supplied again for verification. Portable canonical packets, source authentication and authority integration remain future work. Current API:

```js
const {compile, verify, observe, evalF, meter} = require('./quadratic_ground.js')
const s = {n:4, c:0, l:[3], p:[[0,1],[0,2]]}
const g = compile(s, [])
if (!verify(s, [], g).ok) throw Error('not admitted')
const x = 13n
const answer = evalF(g.decoder, observe(g.rows, x, meter()), meter())
```

## Cost is part of the intention

The reproducible meter counts selected coefficient visits, row tests/XORs, bit-mask scans, dot-product set-bit removals, and symbolic substitution toggles. It is a declared **mixed operation proxy**, not a CPU instruction count, full bit complexity, physical measurement cost, energy, or wall time. BigInt operation width, allocations, sorting, object creation, validation overhead outside ticks, and reading/transporting raw input are not fully metered. Each query supplies a fresh complete raw x to both routes; parity acquisition is explicitly charged in the transformed route. The direct baseline evaluates the supplied expanded ANF, not the best possible optimized quadratic algorithm.

If the raw source has T nonconstant terms, decoder D terms, and observation rows q_i, a bound on the metered warm work per query is

    W = D + sum_i (2 + popcount(q_i)).

It follows from the actual observe/dot/evalF meter. With setup work F (formation plus one independent qualification), direct work on M queries is M*T and admitted-route work <= F+M*W. If T>W, the conservative strict crossover is floor(F/(T-W))+1. This is a proof about this meter and baseline, not an asymptotic complexity improvement or a universal route selector. The initial acquisition and qualification must still be paid; cold one-off requests may prefer direct evaluation. A retained admitted plan is trusted locally; verification is charged once rather than at every warm query.

## Reproducible findings

### Campaign A

[Implementation and campaign](quadratic_ground.js) · [retained evidence](OTG-001-results.json).

168 deterministic small sources (2–8 variables), 12,192 exhaustive state comparisons; additionally exhaustively enumerate all translation differences against all source states and confirm the independent stabilizer cardinality equals 2^(n-rank Q). 326 altered decoder/witness controls refused; work-cap refusal tested. Three 32/64/128-variable structured sources compress to rank five and three decoder terms, but **all three lose at 128 queries once setup and qualification are charged**. Dense random controls are also unfavorable: n=16 requires rank 16, n=32 rank 31; the transformed decoder grows and total work is worse. Retain these as negative results, not suppressed samples.

### Campaign B — distinct held-out representation geometry

[Campaign](reuse_campaign.js) · [retained evidence](OTG-001-reuse-results.json).

Six new source formulas at n=32,64,128. Two hidden independent parity families: randomly permuted disjoint supports and densely overlapping supports. Original expanded ANF is the only input to the solver. Independently compute the held-out oracle using the hidden parity expressions 1+(u1 dot x)(u2 dot x)+(u3 dot x)(u4 dot x)+(u5 dot x). 6,144 held-out queries; 27 additional old-observer refinement sources and 3,456 comparisons. Every structured Ground has rank five and three decoder terms. The cost meter explicitly retains acquisition, warm evaluation, formation and verification.

| n | Geometry | Guaranteed strict crossover (meter) | Direct at 1,024 | Total Ground route at 1,024 |
|---:|---|---:|---:|---:|
| 32 | disjoint | 213 | 93,184 | 39,319 |
| 32 | overlapping | 140 | 239,616 | 71,758 |
| 64 | disjoint | 173 | 358,400 | 93,249 |
| 64 | overlapping | 138 | 1,018,880 | 200,966 |
| 128 | disjoint | 219 | 1,383,424 | 343,765 |
| 128 | overlapping | 195 | 4,170,752 | 901,046 |

The two 128-bit sources reduce direct per-query ANF terms from 1,351/4,073 to 3 after five parity observations. All six routes win at the 1,024-query checkpoint in the declared meter, even with formation and verification. The densely overlapping 128-bit source saves approximately 78.4% inclusive measured work. The exact worst-case warm bound is 324 metered units/query; the 195-query guarantee is conservative for the declared route. No timing speedup or benefit for arbitrary dense quadratics inferred.

## Reproduce

Node.js, no third-party dependencies, from this directory:

```sh
node quadratic_ground.js
node reuse_campaign.js
```

The workflow compares deterministic outputs byte-for-byte with both committed evidence files. The evidence was computed using the same JavaScript functions in a V8 isolate. The isolated run does not imply a completed hosted CI workflow.

## Next experiment

- Treat the polar and radical obstructions as reusable proof-producing constraints on the representation search space; compare against optimized direct factorization, packed bitset quadratic evaluation and linear-algebra baselines rather than just expanded ANF.
- Add canonical source-bound packets and independent replay with actual IFS proof/observation bridges. Measure formation, transport, admission, rejoin and execution separately.
- Extend from a single target to simultaneous target families and source-action pullbacks; distinguish required linear rank from nonlinear feature dimension and exact realized quotient cardinality. For degree >2, higher derivatives form nonlinear constraints; do not assume the one-row radical result survives.
- Add bounded-cost acquisition over an offered row catalogue (TDL-003), where the mathematically ideal coordinate may be unavailable. Keep exact lower-bound witness, refused representation, and actual realization cost separate.
- Investigate a grammar that learns the needed family of transforms itself; compare paid failed candidates and reuse on unseen compatible targets, then apply the approach to more difficult symbolic contractions.

The key research result is that a witnessed failure of one observation language yields a necessary coordinate constraint and, for this exact family, a minimal new linear measurement language. Computation has produced the structure through which later computation becomes cheaper.
