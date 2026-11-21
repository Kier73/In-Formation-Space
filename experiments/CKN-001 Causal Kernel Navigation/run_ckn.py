"""CKN-001 - Causal Kernel Navigation: "invest memory into causality".

Four tiers, one claim each. Pure numpy + stdlib. Deterministic seeds.
    python run_ckn.py            -> prints results and writes results.json beside this file
Everything here runs inside one process on one machine. Nothing touches a network.
"""
import json, os, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
R = {}
rng = np.random.default_rng(90)

# ---------------------------------------------------------------------------
# TIER A - algebraic Ground: Rule 90 on a ring. Kernel of 2^k steps = two dots.
# ---------------------------------------------------------------------------
n = 1_000_003
x0 = rng.integers(0, 2, n, dtype=np.uint8)

def step90(x):
    return np.roll(x, 1) ^ np.roll(x, -1)

def nav90(x, t):
    """f^t = prod over set bits k of (S^{2^k} + S^{-2^k})  (Frobenius in GF(2)[S])."""
    y = x.copy(); k = 0; ops = 0
    while t:
        if t & 1:
            s = pow(2, k, n)
            y = np.roll(y, s) ^ np.roll(y, -s); ops += 1
        t >>= 1; k += 1
    return y, ops

def lucas_cell(x, t, i):
    """Independent oracle: f^t(x)_i = XOR_{j submask of t} x[(i + t - 2j) mod n]."""
    sub = np.zeros(1, dtype=np.int64)
    for b in range(64):
        if (t >> b) & 1:
            sub = np.concatenate([sub, sub + (1 << b)])
    return int(np.bitwise_xor.reduce(x[((i + t - 2 * sub) % n)])), len(sub)

y = x0.copy(); chk = set(rng.integers(1, 3000, 40).tolist()) | {1, 2, 3, 2999}; mism = 0
t0 = time.perf_counter()
for t in range(1, 3000):
    y = step90(y)
    if t in chk:
        mism += int(not np.array_equal(y, nav90(x0, t)[0]))
steps_per_s = 2999 / (time.perf_counter() - t0)
T = 10 ** 18
t0 = time.perf_counter(); yT, opsT = nav90(x0, T); nav_s = time.perf_counter() - t0
cells = rng.integers(0, n, 25).tolist()
t0 = time.perf_counter(); luc = [lucas_cell(x0, T, i) for i in cells]; luc_s = time.perf_counter() - t0
a, b = 7 * 10 ** 17 + 12345, 3 * 10 ** 17 - 12345
R["tierA"] = dict(
    cells=n, horizon=T, popcount=bin(T).count("1"), kernel_ops=opsT, nav_seconds=nav_s,
    direct_steps_per_s=steps_per_s, direct_years_extrapolated=T / steps_per_s / 3.15576e7,
    small_t_mismatches=mism, lucas_cells=len(cells), lucas_terms_per_cell=luc[0][1], lucas_seconds=luc_s,
    lucas_ok=all(luc[k][0] == int(yT[c]) for k, c in enumerate(cells)),
    semigroup_ok=bool(np.array_equal(nav90(nav90(x0, a)[0], b)[0], yT)),
    bit_ops_iterate=float(T) * n, bit_ops_navigate=opsT * n)

# ---------------------------------------------------------------------------
# TIER B - no algebra at all: a 22-bit branching, nonlinear program. Rho Atlas.
# ---------------------------------------------------------------------------
M9 = 511

def vm_step(s):
    s = np.asarray(s, dtype=np.int64)
    A = s & M9; B = (s >> 9) & M9; pc = (s >> 18) & 15
    rotB = ((B << 2) | (B >> 7)) & M9
    nA, nB, npc = A.copy(), B.copy(), (pc + 1) & 15
    c = [pc == k for k in range(16)]
    nA = np.where(c[0], (A + B) & M9, nA)
    nB = np.where(c[1], rotB ^ A, nB)
    npc = np.where(c[2] & ((A & 1) == 1), 5, npc)
    nA = np.where(c[3], (A * 5 + 3) & M9, nA)
    npc = np.where(c[4], 7, npc)
    nB = np.where(c[5], (B + 77) & M9, nB)
    nA = np.where(c[6], A ^ (B >> 3), nA)
    npc = np.where(c[7] & (A > B), 10, npc)
    nB = np.where(c[8], (B * B + 1) & M9, nB)
    npc = np.where(c[9], 11, npc)
    nA = np.where(c[10], (A - B) & M9, nA)
    nB = np.where(c[11], B ^ 0x155, nB)
    npc = np.where(c[12] & (((A ^ B) & 7) == 0), 0, npc)
    nA = np.where(c[13], (A >> 1) | ((B & 1) << 8), nA)
    nB = np.where(c[14], (B + A) & M9, nB)
    npc = np.where(c[15], 0, npc)
    return nA | (nB << 9) | (npc << 18)

N = 1 << 22
tb = {}
t0 = time.perf_counter(); f = vm_step(np.arange(N)).astype(np.int32); tb["map"] = time.perf_counter() - t0
t0 = time.perf_counter()
g = f.copy()
for _ in range(23):
    g = g[g]                                    # f^(2^23); its image = exactly the cyclic states
is_cyc = np.zeros(N, bool); is_cyc[g] = True; tb["cyclic"] = time.perf_counter() - t0
t0 = time.perf_counter()
cyc_id = np.full(N, -1, np.int32); pos = np.full(N, -1, np.int64); order, starts, lens = [], [], []
fl = f.tolist()
for v in np.flatnonzero(is_cyc).tolist():
    if cyc_id[v] >= 0:
        continue
    cid = len(starts); starts.append(len(order)); u = v; mem = []
    while True:
        mem.append(u); u = fl[u]
        if u == v:
            break
    idx = np.array(mem); cyc_id[idx] = cid; pos[idx] = np.arange(len(mem)); order += mem; lens.append(len(mem))
order = np.array(order, np.int64); starts = np.array(starts, np.int64); lens = np.array(lens, np.int64)
tb["cycles"] = time.perf_counter() - t0
t0 = time.perf_counter()
rev = np.argsort(f, kind="stable"); cnt = np.bincount(f, minlength=N); rstart = np.concatenate([[0], np.cumsum(cnt)])
height = np.full(N, -1, np.int64); entry = np.full(N, -1, np.int64)
front = np.flatnonzero(is_cyc); height[front] = 0; entry[front] = front; L = 0
while front.size:
    cc = cnt[front]; tot = int(cc.sum())
    if tot == 0:
        break
    par = np.repeat(front, cc); off = np.arange(tot) - np.repeat(np.cumsum(cc) - cc, cc)
    ch = rev[rstart[par] + off]; keep = height[ch] < 0; ch, par = ch[keep], par[keep]
    L += 1; height[ch] = L; entry[ch] = entry[par]; front = ch
tb["heights"] = time.perf_counter() - t0
H = int(height.max())
t0 = time.perf_counter()
kc = cyc_id[order].astype(np.int64); ko = (order & M9).astype(np.int64)
srt = np.lexsort((pos[order], ko, kc)); inv_key = kc[srt] * 512 + ko[srt]; inv_pos = pos[order][srt]
tb["inverse_index"] = time.perf_counter() - t0
build_s = sum(tb.values())

def fwd(x, t):
    h = int(height[x])
    if t < h:
        for _ in range(t):
            x = fl[x]
        return x
    e = int(entry[x]); c = int(cyc_id[e])
    return int(order[starts[c] + (int(pos[e]) + t - h) % int(lens[c])])

def fwd_all(t):
    c = cyc_id[entry]
    return order[starts[c] + (pos[entry] + ((t - height) % lens[c])) % lens[c]]

def first_hit(x, y):
    """Smallest t >= 0 with register A == y. None = proof that it never happens, for all t."""
    u = x
    for t in range(int(height[x])):
        if (u & M9) == y:
            return t
        u = fl[u]
    c = int(cyc_id[u]); p0 = int(pos[u]); lam = int(lens[c]); k = c * 512 + y
    lo = np.searchsorted(inv_key, k, "left"); hi = np.searchsorted(inv_key, k, "right")
    if lo == hi:
        return None
    ps = inv_pos[lo:hi]; j = np.searchsorted(ps, p0)
    return int(height[x]) + ((int(ps[j]) if j < len(ps) else int(ps[0])) - p0) % lam

def fpow_all(t):                                 # independent oracle: function power by squaring
    res = np.arange(N, dtype=np.int32); base = f.copy()
    while t:
        if t & 1:
            res = base[res]
        base = base[base]; t >>= 1
    return res

V = {}
for TT in [10 ** 18, 2 ** 61 - 1, 10 ** 12 + 7, 3000, H]:
    V[f"all_states_t={TT}"] = bool(np.array_equal(fpow_all(TT), fwd_all(TT)))
xs = rng.integers(0, N, 8192); ys = rng.integers(0, 512, 8192)
chk = set(rng.integers(0, 60000, 60).tolist()) | {0, 1, H - 1, H, H + 1, 59999}
u = xs.astype(np.int64).copy(); hit = np.full(8192, -1, np.int64); fmis = 0
for t in range(60000):
    nw = (hit < 0) & ((u & M9) == ys); hit[nw] = t
    if t in chk:
        fmis += sum(fwd(int(x), t) != int(v) for x, v in zip(xs[:300], u[:300]))
    u = f[u]
found = never = bad = 0
for kk, (x, yv) in enumerate(zip(xs, ys)):
    a_ = first_hit(int(x), int(yv))
    if a_ is None:
        never += 1; bad += int(hit[kk] >= 0)
    else:
        found += 1; bad += int(hit[kk] != a_)
V["direct"] = dict(starts=8192, steps=60000, forward_mismatches=int(fmis), inverse_found=found,
                   inverse_proved_never=never, inverse_disagreements=bad,
                   orbits_fully_covered=bool(H + lens.max() < 60000))
xq = rng.integers(0, N, 20000).tolist()
t0 = time.perf_counter(); [fwd(x, 10 ** 18 + k) for k, x in enumerate(xq)]; qf = (time.perf_counter() - t0) / 20000
t0 = time.perf_counter(); [first_hit(x, k % 512) for k, x in enumerate(xq[:5000])]; qi = (time.perf_counter() - t0) / 5000
s = xq[0]; t0 = time.perf_counter()
for _ in range(200000):
    s = fl[s]
st = (time.perf_counter() - t0) / 200000
R["tierB"] = dict(states=N, build_seconds=tb, build_total=build_s, cyclic_states=int(is_cyc.sum()), cycles=len(lens),
                  cycle_lengths=sorted(lens.tolist(), reverse=True), basin_sizes=sorted(np.bincount(cyc_id[entry]).tolist(), reverse=True),
                  max_tail=H, mean_tail=float(height.mean()), verification=V,
                  forward_query_us=qf * 1e6, inverse_query_us=qi * 1e6, table_step_ns=st * 1e9,
                  iterate_1e18_years=10 ** 18 * st / 3.15576e7, queries_to_repay_build_at_t_1e6=build_s / (st * 1e6))

# ---------------------------------------------------------------------------
# TIER C - negative control: how large is the description of causality?
# ANF of the centre cell after t steps, as a function of its 2t+1 light-cone bits.
# ---------------------------------------------------------------------------
def eca_truth(rule, t):
    w = 2 * t + 1
    cfg = ((np.arange(1 << w)[:, None] >> np.arange(w)) & 1).astype(np.uint8)
    tab = np.array([(rule >> k) & 1 for k in range(8)], np.uint8)
    for _ in range(t):
        cfg = tab[(cfg[:, :-2] << 2) | (cfg[:, 1:-1] << 1) | cfg[:, 2:]]
    return cfg[:, 0], w

def anf(tt, w):
    a_ = tt.copy()
    for i in range(w):
        a_ = a_.reshape(-1, 2, 1 << i); a_[:, 1, :] ^= a_[:, 0, :]; a_ = a_.reshape(-1)
    return a_

pc = np.array([bin(i).count("1") for i in range(1 << 17)], np.int8)
R["tierC"] = {}
for rule in [90, 150, 30, 110]:
    rows = []
    for t in range(1, 9):
        tt, w = eca_truth(rule, t); nz = np.flatnonzero(anf(tt, w))
        rows.append(dict(t=t, cone_bits=w, degree=int(pc[nz].max()), monomials=int(nz.size)))
    R["tierC"][f"rule{rule}"] = rows

# ---------------------------------------------------------------------------
# TIER D - causality as composition order: late-bound summaries of a shuffled stream.
# ---------------------------------------------------------------------------
P = "abracadabra"; alpha = "abcdr"; m = len(P)
fail = [0] * m; k = 0
for i in range(1, m):
    while k and P[i] != P[k]:
        k = fail[k - 1]
    if P[i] == P[k]:
        k += 1
    fail[i] = k
Q = m + 1; Tt = np.zeros((Q, len(alpha)), np.int64)
for q in range(Q):
    for ci, chh in enumerate(alpha):
        s = q if q < m else fail[m - 1]
        while s and P[s] != chh:
            s = fail[s - 1]
        Tt[q, ci] = s + 1 if P[s] == chh else 0
Ltot = 1 << 22; K = 256; Ls = Ltot // K
codes = rng.integers(0, 5, Ltot)
for p in rng.integers(0, Ltot - m, 3000):
    codes[p:p + m] = [alpha.index(c) for c in P]
for p in np.arange(Ls, Ltot, Ls)[:200] - 5:
    codes[p:p + m] = [alpha.index(c) for c in P]            # occurrences straddling segment seams
text = "".join(alpha[c] for c in codes)
truth = 0; i = text.find(P)
while i >= 0:
    truth += 1; i = text.find(P, i + 1)
Tl = Tt.tolist(); s = 0; seq = 0
t0 = time.perf_counter()
for c in codes.tolist():
    s = Tl[s][c]; seq += (s == m)
t_seq = time.perf_counter() - t0
segs = codes.reshape(K, Ls)
t0 = time.perf_counter()
S = np.tile(np.arange(Q), (K, 1)); Cn = np.zeros((K, Q), np.int64)
for j in range(Ls):
    S = Tt[S, segs[:, j][:, None]]; Cn += (S == m)
t_sum = time.perf_counter() - t0
summ = [(S[kk].copy(), Cn[kk].copy()) for kk in range(K)]
compose = lambda A_, B_: (B_[0][A_[0]], A_[1] + B_[1][A_[0]])   # A then B; associative
arrival = rng.permutation(K); received = {int(kk): summ[kk] for kk in arrival}

def tree(lo, hi):
    if hi - lo == 1:
        return received[lo]
    mid = (lo + hi) // 2
    return compose(tree(lo, mid), tree(mid, hi))

tot = tree(0, K)
left = summ[0]
for kk in range(1, K):
    left = compose(left, summ[kk])
wrong = summ[int(arrival[0])]
for kk in arrival[1:]:
    wrong = compose(wrong, summ[int(kk)])
late_ok = True
for q in [4, 7, 10]:
    s = q; c2 = 0
    for c in codes.tolist():
        s = Tl[s][c]; c2 += (s == m)
    late_ok &= (c2 == int(tot[1][q]))
R["tierD"] = dict(stream_chars=Ltot, segments=K, automaton_states=Q, truth=truth, sequential=seq,
                  tree_by_causal_index=int(tot[1][0]), left_fold=int(left[1][0]), composed_in_arrival_order=int(wrong[1][0]),
                  late_binding_ok=bool(late_ok), segments_fully_synchronized=int(sum(len(set(e.tolist())) == 1 for e, _ in summ)),
                  summary_bytes=Q * 16, work_multiplier=Q, critical_path=Ls + int(np.log2(K)), sequential_path=Ltot,
                  t_sequential=t_seq, t_summaries=t_sum)

json.dump(R, open(os.path.join(HERE, "results.json"), "w"), indent=1, default=float)
print(json.dumps(R, indent=1, default=float))
