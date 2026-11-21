"""CKN-003 - Spectral navigation: what the zeta zeros on the critical line can and cannot carry.

1. Compute the first zeros of zeta(1/2+it), t < 6000, from scratch (Riemann-Siegel scan, then
   Euler-Maclaurin refinement), and check them: known values, Gram-point completeness.
2. Local query: recover Lambda(n) (exact prime-power locations) from K zeros through the explicit
   formula with a FIXED declared decoder (cos^2 taper, midpoint difference, threshold log(2)/2).
3. Precision: how many bits each zero must carry for local recovery.
4. Aggregate query: psi(x) for x in [1e6, 1e7] from K zeros, against the RH bound
   |psi(x)-x| <= sqrt(x) log^2 x / (8 pi)  (Schoenfeld 1976, valid for x >= 73.2 under RH).
5. Information accounting: zeros as storage vs bitmap vs a sieve program.

python run_ckn3.py -> writes results_ckn3.json.  numpy + stdlib, one process, no network.
"""
import json, math, os, time
from math import factorial
import numpy as np

HERE = globals().get("HERE_OVERRIDE") or os.path.dirname(os.path.abspath(__file__))
R = {}
T_MAX = 6000.0

# ---------------------------------------------------------------- 1. zeros
def theta(t):
    t = np.asarray(t, float)
    return t / 2 * np.log(t / (2 * np.pi)) - t / 2 - np.pi / 8 + 1 / (48 * t) + 7 / (5760 * t ** 3) + 31 / (80640 * t ** 5)

def Z_rs(t):
    """Riemann-Siegel Z with the first correction term C0 (fast, ~1e-3 accurate in location)."""
    t = np.atleast_1d(np.asarray(t, float)); a = np.sqrt(t / (2 * np.pi)); Nn = np.floor(a).astype(int); th = theta(t)
    out = np.zeros_like(t)
    for n in range(1, int(Nn.max()) + 1):
        m = Nn >= n
        out[m] += np.cos(th[m] - t[m] * np.log(n)) / np.sqrt(n)
    out *= 2
    p = a - Nn; sgn = np.where(Nn % 2 == 1, 1.0, -1.0)
    return out + sgn * a ** -0.5 * np.cos(2 * np.pi * (p * p - p - 1 / 16)) / np.cos(2 * np.pi * p)

B2 = [1 / 6, -1 / 30, 1 / 42, -1 / 30, 5 / 66, -691 / 2730, 7 / 6, -3617 / 510]

def Z_em(t):
    """Independent evaluator: Euler-Maclaurin zeta(1/2+it) rotated by e^{i theta}."""
    t = np.atleast_1d(np.asarray(t, float)); s = 0.5 + 1j * t
    Nn = int(max(t.max() * 0.5, 30)); acc = np.zeros(t.size, complex)
    for n in range(1, Nn):
        acc += np.exp(-s * np.log(n))
    NN = float(Nn); Ns = np.exp(-s * np.log(NN)); acc += NN * Ns / (s - 1) + Ns / 2
    poch = s.copy(); term = Ns / NN
    for k, b in enumerate(B2, start=1):
        acc += b / factorial(2 * k) * poch * term
        poch = poch * (s + 2 * k - 1) * (s + 2 * k); term = term / (NN * NN)
    return (np.exp(1j * theta(t)) * acc).real

def bisect(f, lo, hi, it):
    flo = f(lo)
    for _ in range(it):
        mid = (lo + hi) / 2; fm = f(mid); same = np.sign(fm) == np.sign(flo)
        lo = np.where(same, mid, lo); flo = np.where(same, fm, flo); hi = np.where(same, hi, mid)
    return (lo + hi) / 2

t0 = time.perf_counter()
grid = np.arange(10.0, T_MAX, 0.01); zg = np.empty_like(grid)
for i in range(0, grid.size, 50000):
    zg[i:i + 50000] = Z_rs(grid[i:i + 50000])
idx = np.flatnonzero(np.sign(zg[:-1]) != np.sign(zg[1:]))
g0 = bisect(Z_rs, grid[idx].copy(), grid[idx + 1].copy(), 45)
del grid, zg
gl = np.concatenate([[1.0], np.diff(g0)]); gr = np.concatenate([np.diff(g0), [1.0]])
d = np.minimum(0.02, np.minimum(gl, gr) / 2.5)
gam = np.empty_like(g0); sign_ok = 0
for i in range(0, g0.size, 400):
    lo, hi = g0[i:i + 400] - d[i:i + 400], g0[i:i + 400] + d[i:i + 400]
    sign_ok += int(np.sum(np.sign(Z_em(lo)) != np.sign(Z_em(hi))))
    gam[i:i + 400] = bisect(Z_em, lo, hi, 36)
zeros_s = time.perf_counter() - t0
known = {1: 14.134725142, 2: 21.022039639, 3: 25.010857580, 4: 30.424876126, 5: 32.935061588, 6: 37.586178159,
         7: 40.918719012, 8: 43.327073281, 9: 48.005150881, 10: 49.773832478, 100: 236.524229666, 1000: 1419.422480946}
n_ar = np.arange(0, gam.size); gpt = np.maximum(18.0 + n_ar * 1.0, 2 * np.pi * np.e)
for _ in range(60):
    gpt = gpt - (theta(gpt) - n_ar * np.pi) / (0.5 * np.log(gpt / (2 * np.pi)))
keep = gpt < T_MAX - 1; gpt, n_ar = gpt[keep], n_ar[keep]
zG = np.concatenate([Z_em(gpt[i:i + 400]) for i in range(0, gpt.size, 400)])
good = ((-1.0) ** n_ar * zG) > 0
dev = np.searchsorted(gam, gpt[good]) - (n_ar[good] + 1)
R["zeros"] = dict(count=int(gam.size), t_max=T_MAX, seconds=zeros_s, refined_brackets_with_sign_change=sign_ok,
                  max_abs_error_vs_known=float(max(abs(gam[k - 1] - v) for k, v in known.items())),
                  min_gap=float(np.diff(gam).min()), gram_points=int(gpt.size), good_gram_points=int(good.sum()),
                  good_gram_count_deviations=int(np.count_nonzero(dev)))
np.save(os.path.join(HERE, "zeta_zeros_t6000.npy"), gam)

# ---------------------------------------------------------------- 2. local recovery
NMAX = 4000
sv = np.ones(NMAX + 1, bool); sv[:2] = False
for p in range(2, int(NMAX ** 0.5) + 1):
    if sv[p]:
        sv[p * p::p] = False
Lam = np.zeros(NMAX + 1)
for p in np.flatnonzero(sv):
    q = p
    while q <= NMAX:
        Lam[q] = np.log(p); q *= p

def psi_spec(x, gk, w):
    x = np.asarray(x, float); L = np.log(x); out = np.zeros_like(x); rho = 0.5 + 1j * gk
    for i in range(0, gk.size, 150):
        r = rho[i:i + 150]
        out += 2 * ((np.exp(np.outer(L, r)) / r) * w[i:i + 150]).real.sum(1)
    return x - out - np.log(2 * np.pi) - 0.5 * np.log(1 - x ** -2.0)

def recover(K, gsrc=None, weight="cos2"):
    gk = (gam if gsrc is None else gsrc)[:K]; T = gam[K] if K < gam.size else T_MAX
    w = {"cos2": np.cos(np.pi * gk / (2 * T)) ** 2, "fejer": 1 - gk / T, "sharp": np.ones_like(gk)}[weight]
    nmax = int(min(NMAX, 0.6 * T)); n = np.arange(2, nmax + 1)
    D = psi_spec(n + 0.5, gk, w) - psi_spec(n - 0.5, gk, w); tr = Lam[2:nmax + 1]
    wrong = np.flatnonzero((D > 0.5 * np.log(2)) != (tr > 0)); n0 = int(n[wrong[0]] - 1) if wrong.size else nmax
    return dict(K=K, T=float(T), weight=weight, perfect_up_to=n0, n0_over_T=n0 / float(T),
                prime_powers_resolved=int((tr[:n0 - 1] > 0).sum()), max_abs_err_below_n0=float(np.abs(D - tr)[:n0 - 1].max()))

R["local"] = [recover(K) for K in [125, 250, 500, 1000, 2000, 4000, gam.size]]
R["local_taper_comparison_K2000"] = [recover(2000, weight=w) for w in ["sharp", "fejer", "cos2"]]
Ts = np.array([r["T"] for r in R["local"]]); n0s = np.array([r["perfect_up_to"] for r in R["local"]])
R["local_loglog_slope"] = float(np.polyfit(np.log(Ts), np.log(n0s), 1)[0])

# ---------------------------------------------------------------- 3. precision
rngp = np.random.default_rng(3)
R["precision_K2000"] = [dict(eps=e, perfect_up_to=recover(2000, gsrc=gam + rngp.normal(0, e, gam.size))["perfect_up_to"])
                        for e in [1e-1, 3e-2, 1e-2, 3e-3, 1e-3, 1e-4, 1e-6]]

# ---------------------------------------------------------------- 4. aggregate psi(x)
XM = 10_000_000
sv2 = np.ones(XM + 1, bool); sv2[:2] = False
for p in range(2, int(XM ** 0.5) + 1):
    if sv2[p]:
        sv2[p * p::p] = False
P = np.flatnonzero(sv2); del sv2
cl = np.cumsum(np.log(P)); pp = []
for p in P[P <= int(XM ** 0.5)].tolist():
    q = p * p
    while q <= XM:
        pp.append((q, math.log(p))); q *= p
pp.sort(); ppx = np.array([a for a, _ in pp]); ppl = np.cumsum([b for _, b in pp])

def psi_exact(x):
    i = np.searchsorted(P, x, "right"); j = np.searchsorted(ppx, x, "right")
    return np.where(i > 0, cl[np.maximum(i - 1, 0)], 0) + np.where(j > 0, ppl[np.maximum(j - 1, 0)], 0)

xs = np.exp(rngp.uniform(np.log(1e6), np.log(1e7), 300)) + 0.37
ex = psi_exact(xs); rh = np.sqrt(xs) * np.log(xs) ** 2 / (8 * np.pi)
R["rh_bound_holds_all_300"] = bool(np.all(np.abs(ex - xs) <= rh))
agg = []
for K in [0, 10, 30, 100, 300, 1000, 3000, gam.size]:
    ap = xs - np.log(2 * np.pi) - 0.5 * np.log(1 - xs ** -2.0) if K == 0 else psi_spec(xs, gam[:K], np.ones(K))
    e = np.abs(ap - ex)
    agg.append(dict(K=K, rms_err_over_sqrtx=float(np.sqrt(np.mean((e / np.sqrt(xs)) ** 2))),
                    max_err_over_RH_bound=float((e / rh).max()),
                    median_bits_beyond_RH_bound=float(np.median(np.log2(rh / np.maximum(e, 1e-9))))))
R["aggregate"] = agg
kk = np.array([a["K"] for a in agg[1:]], float); rr = np.array([a["rms_err_over_sqrtx"] for a in agg[1:]])
R["aggregate_rms_vs_K_exponent"] = float(np.polyfit(np.log(kk), np.log(rr), 1)[0])

# ---------------------------------------------------------------- 5. information accounting
n0 = R["local"][-1]["perfect_up_to"]
bits_per_zero = math.log2(1.0 / 0.01)          # gap-coded to the measured sufficient precision (~0.01)
R["accounting_local"] = dict(
    primes_exactly_recovered_up_to=n0, zeros_used=int(gam.size),
    zero_storage_bits=int(gam.size * bits_per_zero), bitmap_bits=n0, odd_only_bitmap_bits=n0 // 2,
    ratio_zero_storage_to_bitmap=gam.size * bits_per_zero / n0,
    note="A sieve program of a few hundred bytes regenerates the same primes; zeros are not a compression of local prime data.")
R["accounting_aggregate"] = dict(
    x=1e7, exact_sieve_element_ops=XM, spectral_terms=int(gam.size),
    spectral_rms_error=float(agg[-1]["rms_err_over_sqrtx"] * math.sqrt(1e7)),
    rh_bound_at_1e7=float(math.sqrt(1e7) * math.log(1e7) ** 2 / (8 * math.pi)))
json.dump(R, open(os.path.join(HERE, "results_ckn3.json"), "w"), indent=1, default=float)
print(json.dumps(R, indent=1, default=float))
