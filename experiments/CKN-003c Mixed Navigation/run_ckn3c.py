"""CKN-003c - Mixed navigation: the n-th prime, exactly, from three tiers of knowledge.

Query: given n, return p_n exactly.  Correctness never depends on an estimate:
    x_hat  <- estimate (unconditional bracket | RH-certified li | smooth R | R + K zeta zeros)
    c      <- pi(x_hat), EXACT (Lucy_Hedgehog, O(x^3/4))          = one "anchor"
    p_n    <- segmented sieve outward from x_hat, EXACT, until the count reaches n
An estimate only changes how many anchors / how many sieved numbers are needed. Answers are
verified by known values (OEIS A006988), deterministic Miller-Rabin, and pi(p)=n (p prime and pi(p)=n => p = p_n).

python run_ckn3c.py  (needs zeta_zeros_t6000.npy from run_ckn3.py)  -> results_ckn3c.json
"""
import json, math, os, time
from math import isqrt
import numpy as np

HERE = globals().get("HERE_OVERRIDE") or os.path.dirname(os.path.abspath(__file__))
gam = np.load(os.path.join(HERE, "zeta_zeros_t6000.npy"))
R = {}

# ------------------------------------------------------------------ exact tools
def lucy_pi(n):
    r = isqrt(n)
    small = np.arange(-1, r, dtype=np.int64); small[0] = 0
    idx = np.arange(1, r + 1, dtype=np.int64); large = np.zeros(r + 1, np.int64); large[1:] = n // idx - 1
    for p in range(2, r + 1):
        if small[p] == small[p - 1]:
            continue
        sp = small[p - 1]; p2 = p * p; imax = min(r, n // p2)
        CH = 1 << 18                      # chunked: bounded temporaries (reads use pre-update values,
        ib = min(imax, r // p)            # exactly as the sequential algorithm; see note in README)
        if ib >= 1:                       # i*p <= r  -> read large[i*p]  (i*p > i: not yet updated)
            for a in range(1, ib + 1, CH):
                b = min(ib, a + CH - 1)
                large[a:b + 1] -= large[np.arange(a, b + 1, dtype=np.int64) * p] - sp
        for a in range(ib + 1, imax + 1, CH):   # i*p > r -> read small[n // (i*p)] (small not yet updated)
            b = min(imax, a + CH - 1)
            large[a:b + 1] -= small[n // (np.arange(a, b + 1, dtype=np.int64) * p)] - sp
        if p2 <= r:                       # descending-order semantics: process chunks from the top down
            for hi_ in range(r + 1, p2, -CH):
                lo_ = max(p2, hi_ - CH)
                small[lo_:hi_] -= small[np.arange(lo_, hi_, dtype=np.int64) // p] - sp
    return int(large[1])

_base = {"lim": 1, "P": np.array([], np.int64)}
def base_primes(lim):
    if lim > _base["lim"]:
        s = np.ones(lim + 1, bool); s[:2] = False
        for p in range(2, isqrt(lim) + 1):
            if s[p]:
                s[p * p::p] = False
        _base["lim"], _base["P"] = lim, np.flatnonzero(s).astype(np.int64)
    return _base["P"][_base["P"] <= lim]

def sieve_block(lo, hi):
    """Primes in [lo, hi)."""
    lo = max(lo, 2); seg = np.ones(hi - lo, bool)
    for p in base_primes(isqrt(hi) + 1).tolist():
        st = max(p * p, ((lo + p - 1) // p) * p)
        if st >= hi:
            if p * p >= hi:
                break
            continue
        seg[st - lo::p] = False
    return np.flatnonzero(seg).astype(np.int64) + lo

def walk(x, c, n, block=1 << 16):
    """Given exact c = pi(x), find p_n by sieving away from x. Returns (p_n, numbers_sieved)."""
    sieved = 0
    if c < n:                                   # need (n-c) more primes above x
        need, lo = n - c, x + 1
        while True:
            pr = sieve_block(lo, lo + block); sieved += block
            if pr.size >= need:
                return int(pr[need - 1]), sieved
            need -= pr.size; lo += block
    else:                                       # p_n <= x: the (c-n+1)-th prime counting down from x
        k, hi = c - n + 1, x + 1
        while True:
            lo = max(2, hi - block); pr = sieve_block(lo, hi); sieved += hi - lo
            if pr.size >= k:
                return int(pr[pr.size - k]), sieved
            k -= pr.size; hi = lo

def is_prime_mr(n):
    """Deterministic for n < 3.3e24 with the first 13 prime bases (Sorenson-Webster 2015)."""
    if n < 2:
        return False
    B = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41]
    for p in B:
        if n % p == 0:
            return n == p
    d, r = n - 1, 0
    while d % 2 == 0:
        d //= 2; r += 1
    for a in B:
        x = pow(a, d, n)
        if x in (1, n - 1):
            continue
        for _ in range(r - 1):
            x = x * x % n
            if x == n - 1:
                break
        else:
            return False
    return True

# ------------------------------------------------------------------ estimators
def zeta_int(k):
    return sum(j ** -k for j in range(1, 200)) + 200 ** (1 - k) / (k - 1) + 0.5 * 200 ** -k
ZT = [None, None] + [zeta_int(k) for k in range(2, 260)]

def R_smooth(x):
    L = math.log(x); s = 1.0; term = 1.0
    for k in range(1, 250):
        term *= L / k; inc = term / (k * ZT[k + 1]); s += inc
        if inc < 1e-18 * s:
            break
    return s

def li(x):
    L = math.log(x); g = 0.5772156649015329; tot = 0.0; term = 1.0; inner = 0.0
    for k in range(1, 200):
        term *= L / k
        if (k - 1) % 2 == 0:
            inner += 1.0 / (2 * ((k - 1) // 2) + 1)
        tot += ((-1) ** (k - 1)) * term / (2 ** (k - 1)) * inner
    return g + math.log(L) + math.sqrt(x) * tot

MU = {1: 1, 2: -1, 3: -1}
def pi_spec(x, K):
    """R(x) - sum_m mu(m)/m * 2Re sum_{k<=K} li(x^(rho_k/m)), sharp truncation (best on 60-point test)."""
    if K == 0:
        return R_smooth(x)
    out = R_smooth(x)
    for m, mu in MU.items():
        W = (0.5 + 1j * gam[:K]) * (math.log(x) / m)
        out -= mu / m * 2 * float((np.exp(W) / W * (1 + 1 / W + 2 / W ** 2 + 6 / W ** 3 + 24 / W ** 4)).real.sum())
    return out

def invert(f, n):
    x = n * (math.log(n) + math.log(math.log(n)) - 1)
    for _ in range(60):
        dx = (n - f(x)) * math.log(x); x += dx
        if abs(dx) < 0.5:
            break
    return int(round(x))

def rh_band(n):
    """Under RH (Schoenfeld 1976, x >= 2657): |pi(x) - li(x)| < sqrt(x) ln x / (8 pi).
    Returns the certified interval of x where p_n can lie, and its width in numbers."""
    x0 = invert(li, n); B = math.sqrt(x0) * math.log(x0) / (8 * math.pi) * 1.01
    lo = invert(li, n - B); hi = invert(li, n + B)
    return x0, lo, hi

# ------------------------------------------------------------------ methods
def m_bracket(n, W=1 << 22):
    """No estimate: unconditional Rosser/Dusart bracket n(ln n+lnln n-1) < p_n < n(ln n+lnln n), n>=6,
    binary search with exact anchors until the bracket is <= W wide, then sieve."""
    L = math.log(n); lo = int(n * (L + math.log(L) - 1)); hi = int(n * (L + math.log(L))) + 1
    anchors = 0; t0 = time.perf_counter(); c_lo = None; w0 = hi - lo
    while hi - lo > W:
        mid = (lo + hi) // 2; c = lucy_pi(mid); anchors += 1
        if c >= n:
            hi = mid
        else:
            lo, c_lo = mid, c
    if c_lo is None:
        c_lo = lucy_pi(lo); anchors += 1
    p, sv = walk(lo, c_lo, n)
    return dict(p=p, anchors=anchors, sieved=sv, seconds=time.perf_counter() - t0, bracket_start=int(w0))

def m_estimate(n, f):
    t0 = time.perf_counter(); x = invert(f, n); te = time.perf_counter() - t0
    t1 = time.perf_counter(); c = lucy_pi(x); ta = time.perf_counter() - t1
    t2 = time.perf_counter(); p, sv = walk(x, c, n); tw = time.perf_counter() - t2
    return dict(p=p, x_hat=x, primes_off=c - n, distance=abs(p - x), anchors=1, sieved=sv,
                seconds=te + ta + tw, t_estimate=te, t_anchor=ta, t_walk=tw)

# ------------------------------------------------------------------ 1. exact counter validation
known_pi = {10 ** 9: 50847534, 10 ** 10: 455052511, 10 ** 11: 4118054813, 10 ** 12: 37607912018, 10 ** 13: 346065536839}
R["lucy_validation"] = {}
for x, v in known_pi.items():
    t0 = time.perf_counter(); g = lucy_pi(x)
    R["lucy_validation"][f"1e{int(math.log10(x))}"] = dict(ok=g == v, seconds=time.perf_counter() - t0)

# ------------------------------------------------------------------ 2. headline queries
KNOWN_PN = {10 ** 8: 2038074743, 10 ** 9: 22801763489, 10 ** 10: 252097800623,
            10 ** 11: 2760727302517, 10 ** 12: 29996224275833}
F = {"li_RH": li, "R_smooth": R_smooth, "R+100_zeros": lambda x: pi_spec(x, 100),
     "R+1000_zeros": lambda x: pi_spec(x, 1000), "R+5598_zeros": lambda x: pi_spec(x, gam.size)}
heads = {}
for n, pk in KNOWN_PN.items():
    row = {}
    x0, blo, bhi = rh_band(n)
    row["RH_certified_band_numbers"] = bhi - blo
    row["RH_certified_max_walk_numbers"] = max(x0 - blo, bhi - x0)
    for name, f in F.items():
        if n >= 10 ** 12 and name not in ("R_smooth", "R+5598_zeros"):
            continue                              # each anchor at x~3e13 costs ~1 min; keep the run short
        r = m_estimate(n, f); r["correct"] = r["p"] == pk; row[name] = r
    if n <= 10 ** 10:
        r = m_bracket(n); r["correct"] = r["p"] == pk; row["no_estimate_bracket"] = r
    p = row["R+5598_zeros"]["p"]; t0 = time.perf_counter()
    cp = lucy_pi(p)
    row["verify"] = dict(known=pk, matches_known=p == pk, mr_prime=is_prime_mr(p), pi_p_eq_n=cp == n,
                         seconds=time.perf_counter() - t0)
    heads[f"1e{int(math.log10(n))}"] = row
R["headline"] = heads

# ------------------------------------------------------------------ 3. batch statistics (random n)
rng = np.random.default_rng(2026)
ns = sorted(int(v) for v in np.exp(rng.uniform(math.log(1e8), math.log(1e10), 40)))
stats = {k: [] for k in ["R_smooth", "R+1000_zeros", "R+5598_zeros"]}
for n in ns:
    for name in stats:
        r = m_estimate(n, F[name]); stats[name].append((n, r["primes_off"], r["sieved"], r["p"], r["x_hat"]))
agree = all(len({s[i][3] for s in stats.values()}) == 1 for i in range(len(ns)))
mr_ok = all(is_prime_mr(s[3]) for s in stats["R+5598_zeros"])
R["batch"] = dict(queries=len(ns), n_range=[ns[0], ns[-1]], all_methods_same_answer=agree, all_answers_mr_prime=mr_ok,
                  per_method={k: dict(median_abs_primes_off=float(np.median([abs(v[1]) for v in s])),
                                      max_abs_primes_off=int(max(abs(v[1]) for v in s)),
                                      median_sieved=float(np.median([v[2] for v in s])),
                                      median_distance=float(np.median([abs(v[3] - v[4]) for v in s])),
                                      max_distance=int(max(abs(v[3] - v[4]) for v in s)),
                                      total_sieved=int(sum(v[2] for v in s))) for k, s in stats.items()})

# ------------------------------------------------------------------ 4. pure-sieve baseline (throughput)
t0 = time.perf_counter(); lo = 10 ** 9; tot = 0
for b in range(40):
    tot += sieve_block(lo + b * (1 << 20), lo + (b + 1) * (1 << 20)).size
rate = 40 * (1 << 20) / (time.perf_counter() - t0)
R["pure_sieve"] = dict(numbers_per_second=rate,
                       extrapolated_seconds={k: KNOWN_PN[10 ** int(k[2:])] / rate for k in heads})

json.dump(R, open(os.path.join(HERE, "results_ckn3c.json"), "w"), indent=1, default=float)
print(json.dumps(R, indent=1, default=float))
