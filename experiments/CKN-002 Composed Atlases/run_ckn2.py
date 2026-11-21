"""CKN-002 - Composed atlases: navigating state spaces far larger than any table.

Part P (product):  8 independent 20-bit programs = one 160-bit machine (2^160 states).
                   Forward navigation + joint inverse queries ("first t at which ALL eight
                   registers show their targets") solved by CRT over residue sets.
Part C (cascade):  a 20-bit sender drives a 20-bit receiver through a 4-bit symbol port
                   (2^40 joint states). Navigated through the HOLONOMY: the receiver map
                   induced by one full period of the sender's symbol stream.
Part N (negative control): admission budget for holonomy; when it must refuse.

python run_ckn2.py  -> prints and writes results_ckn2.json. One process, one machine, no network.
"""
import json, os, time
from array import array
from math import gcd, log10
import numpy as np

HERE = globals().get("HERE_OVERRIDE") or os.path.dirname(os.path.abspath(__file__))
R = {}
BITS = 20; N = 1 << BITS; AR = np.arange(N); OBS = (AR & 255).astype(np.int32)
rng = np.random.default_rng(2002)

# ==== SECTION 0: machinery =========================================================
def make_program(seed, with_input=False):
    r = np.random.default_rng(seed)
    menu = list(range(12)) + ([12, 13, 14, 15] if with_input else [])
    prog = [(int(r.choice(menu)), int(r.integers(1, 256)), int(r.integers(1, 8)), int(r.integers(0, 16)),
             int(r.integers(0, 128)) * 2 + 1) for _ in range(16)]
    if with_input:                                   # guarantee the receiver reads its port
        for k in r.choice(16, 4, replace=False):
            prog[int(k)] = (int(r.choice([12, 13, 14, 15])),) + prog[int(k)][1:]
    return prog

def run_program(prog, s, u=0):
    """One step of a 16-instruction machine: A,B 8-bit registers, 4-bit pc; u = input port."""
    s = np.asarray(s, dtype=np.int64)
    A = s & 255; B = (s >> 8) & 255; pc = (s >> 16) & 15
    nA, nB, npc = A.copy(), B.copy(), (pc + 1) & 15
    for k, (op, c, sh, tgt, odd) in enumerate(prog):
        m = pc == k
        if op == 0: nA = np.where(m, (A + B + c) & 255, nA)
        elif op == 1: nB = np.where(m, (((B << sh) | (B >> (8 - sh))) & 255) ^ A, nB)
        elif op == 2: npc = np.where(m & ((A & c) != 0), tgt, npc)
        elif op == 3: nA = np.where(m, (A * odd + c) & 255, nA)
        elif op == 4: nB = np.where(m, (B * B + c) & 255, nB)
        elif op == 5: npc = np.where(m & (A > B), tgt, npc)
        elif op == 6: nA = np.where(m, A ^ (B >> sh), nA)
        elif op == 7: nB = np.where(m, (B + A) & 255, nB)
        elif op == 8: nA = np.where(m, (A - B) & 255, nA)
        elif op == 9: npc = np.where(m, tgt, npc)
        elif op == 10: nB = np.where(m, B ^ c, nB)
        elif op == 11: npc = np.where(m & (((A ^ B) & 7) == 0), tgt, npc)
        elif op == 12: nA = np.where(m, (A + u * odd) & 255, nA)
        elif op == 13: nB = np.where(m, B ^ ((u << sh) & 255), nB)
        elif op == 14: npc = np.where(m & ((u & ((c & 15) | 1)) != 0), tgt, npc)
        elif op == 15: nA = np.where(m, (A ^ u ^ (B >> sh)) & 255, nA)
    return nA | (nB << 8) | (npc << 16)

class Atlas:
    """Rho atlas of a finite map f: tail height, cycle id, cycle phase, entry point, inverse index."""
    def __init__(self, f, obs):
        t0 = time.perf_counter()
        f = np.ascontiguousarray(f, dtype=np.int32); n = f.size
        self.f, self.n = f, n; self.obs = np.ascontiguousarray(obs, dtype=np.int32); self.obsl = memoryview(self.obs); self.fl = fl = memoryview(f)
        g = f.copy()
        for _ in range(n.bit_length()):
            g = g[g]                                   # image of f^(2^bits) = cyclic states
        cyc = np.zeros(n, bool); cyc[g] = True
        cid = np.full(n, -1, np.int32); pos = np.full(n, -1, np.int32); order, starts, lens = [], [], []
        seen = array('i', cid.tobytes())
        for v in np.flatnonzero(cyc).tolist():
            if seen[v] >= 0:
                continue
            mem = [v]; u = fl[v]
            while u != v:
                mem.append(u); u = fl[u]
            for w in mem:
                seen[w] = len(lens)
            idx = np.asarray(mem); cid[idx] = len(lens); pos[idx] = np.arange(len(mem))
            starts.append(len(order)); order.extend(mem); lens.append(len(mem))
        rev = np.argsort(f, kind="stable"); cnt = np.bincount(f, minlength=n); rs = np.concatenate([[0], np.cumsum(cnt)])
        h = np.full(n, -1, np.int32); e = np.full(n, -1, np.int32)
        fr = np.flatnonzero(cyc); h[fr] = 0; e[fr] = fr; L = 0
        while fr.size:
            cc = cnt[fr]; tot = int(cc.sum())
            if tot == 0:
                break
            par = np.repeat(fr, cc); off = np.arange(tot) - np.repeat(np.cumsum(cc) - cc, cc)
            ch = rev[rs[par] + off]; keep = h[ch] < 0; ch, par = ch[keep], par[keep]
            L += 1; h[ch] = L; e[ch] = e[par]; fr = ch
        oc = np.asarray(order, np.int64); self.K = K = int(self.obs.max()) + 1
        kc = cid[oc].astype(np.int64); ko = self.obs[oc].astype(np.int64); pc = pos[oc]
        srt = np.lexsort((pc, ko, kc)); self.inv_key = (kc * K + ko)[srt]; self.inv_pos = pc[srt]
        self.order, self.starts, self.lens = oc, np.array(starts, np.int64), np.array(lens, np.int64)
        self.cid, self.pos, self.h, self.e = cid, pos, h, e
        self.hl, self.el, self.cidl, self.posl = (memoryview(v) for v in (h, e, cid, pos))
        self.orderl, self.startsl, self.lensl = memoryview(oc), list(starts), list(lens)
        self.H = int(h.max()); self.build_s = time.perf_counter() - t0

    def fwd(self, x, t):
        h = self.hl[x]
        if t < h:
            fl = self.fl
            for _ in range(t):
                x = fl[x]
            return x
        e = self.el[x]; c = self.cidl[e]
        return self.orderl[self.startsl[c] + (self.posl[e] + (t - h)) % self.lensl[c]]

    def fwd_vec(self, xs, t):
        xs = np.asarray(xs, np.int64)
        if t < self.H:
            for _ in range(t):
                xs = self.f[xs]
            return xs.astype(np.int64)
        e = self.e[xs]; c = self.cid[e]; lam = self.lens[c]
        tm = np.array([t % int(l) for l in self.lens], np.int64)[c]
        ph = (self.pos[e].astype(np.int64) + tm - self.h[xs].astype(np.int64)) % lam
        return self.order[self.starts[c] + ph]

    def residues(self, x, y):
        """(tail h, cycle length lam, residues r: for t>=h, obs(f^t x)=y  <=>  t mod lam in R)."""
        h = self.hl[x]; fl = self.fl; u = x
        for _ in range(h):
            u = fl[u]
        c = self.cidl[u]; p0 = self.posl[u]; lam = self.lensl[c]; k = c * self.K + y
        lo = int(np.searchsorted(self.inv_key, k, "left")); hi = int(np.searchsorted(self.inv_key, k, "right"))
        return h, lam, sorted({(int(p) - p0 + h) % lam for p in self.inv_pos[lo:hi]})

def crt_merge(comps, Hm, cap=4_000_000):
    """Smallest t >= Hm with t mod lam_i in R_i for all i, or None (a proof of 'never')."""
    L, Rc, peak = 1, [0], 1
    for i, (h, lam, Rs) in enumerate(comps):
        if not Rs:
            return None, dict(regime="never", reason=f"component {i} never shows its target on its cycle", L=L, peak=peak)
        g = gcd(L, lam); lg = lam // g; inv = pow((L // g) % lg, -1, lg) if lg > 1 else 0
        by = {}
        for s in Rs:
            by.setdefault(s % g, []).append(s)
        new = set()
        for r in Rc:
            for s in by.get(r % g, ()):
                new.add(r + L * ((((s - r) // g) * inv) % lg))
        Rc, L = list(new), L * lg; peak = max(peak, len(Rc))
        if not Rc:
            return None, dict(regime="never", reason=f"residue classes incompatible when adding component {i}", L=L, peak=peak)
        if len(Rc) > cap:
            raise RuntimeError("residue-class explosion; refuse rather than guess")
    return min(Hm + (r - Hm) % L for r in Rc), dict(regime="periodic", L=L, peak=peak, classes=len(Rc))

def joint_atlas(ats, xs, ys):
    comps = [a.residues(x, y) for a, x, y in zip(ats, xs, ys)]
    Hm = max(c[0] for c in comps); st = list(xs)
    for t in range(Hm):                                      # pre-periodic window, observed directly
        if all(a.obsl[s] == y for a, s, y in zip(ats, st, ys)):
            return t, dict(regime="pre-periodic", L=None, peak=0)
        st = [a.fl[s] for a, s in zip(ats, st)]
    return crt_merge(comps, Hm)

# ---- independent oracles (never read the atlas) ----
def brent(fl, x0):
    power = lam = 1; tort = x0; hare = fl[x0]
    while tort != hare:
        if power == lam:
            tort = hare; power *= 2; lam = 0
        hare = fl[hare]; lam += 1
    tort = hare = x0
    for _ in range(lam):
        hare = fl[hare]
    mu = 0
    while tort != hare:
        tort = fl[tort]; hare = fl[hare]; mu += 1
    seq = array('i', [x0]); u = x0
    for _ in range(mu + lam - 1):
        u = fl[u]; seq.append(u)
    return mu, lam, seq

def o1_state(b, t):
    mu, lam, seq = b
    return seq[t] if t < mu + lam else seq[mu + (t - mu) % lam]

def joint_brent(brs, obsl, ys):
    Hm = max(b[0] for b in brs)
    for t in range(Hm):
        if all(ob[o1_state(b, t)] == y for b, ob, y in zip(brs, obsl, ys)):
            return t, dict(regime="pre-periodic")
    comps = [(mu, lam, sorted({t % lam for t in range(mu, mu + lam) if ob[seq[t]] == y}))
             for (mu, lam, seq), ob, y in zip(brs, obsl, ys)]
    return crt_merge(comps, Hm)

def sieve_first(obs_np, brs, ys, limit=30_000_000):
    mu_max = max(b[0] for b in brs); L = 1
    for b in brs:
        L = L * b[1] // gcd(L, b[1])
    bound = mu_max + L
    if bound > limit:
        return "skip", bound
    acc = np.ones(bound, bool)
    for ob, (mu, lam, seq), y in zip(obs_np, brs, ys):
        m = ob[np.frombuffer(seq, dtype=np.int32)] == y
        arr = np.empty(bound, bool); arr[:mu] = m[:mu]; arr[mu:] = np.resize(m[mu:], bound - mu); acc &= arr
    i = int(np.argmax(acc))
    return (i if acc[i] else None), bound

def fpow(f, t):
    res = np.arange(f.size, dtype=np.int32); base = f.astype(np.int32)
    while t:
        if t & 1:
            res = base[res]
        base = base[base]; t >>= 1
    return res

# ==== SECTION 1: components ========================================================
# Deterministic selection rule, fixed before any query: scan seeds 1000.., keep programs with
# <= 12 cycles and longest cycle >= 300 (non-degenerate dynamics), take the first 8.
t0 = time.perf_counter(); comps_at, seeds = [], []
for seed in range(1000, 1100):
    at = Atlas(run_program(make_program(seed), AR), OBS)
    if len(at.lensl) <= 12 and max(at.lensl) >= 300:
        comps_at.append(at); seeds.append(seed)
    if len(comps_at) == 8:
        break
R["components"] = [dict(seed=s, cycles=sorted(a.lensl, reverse=True), max_tail=a.H, build_s=round(a.build_s, 3))
                   for s, a in zip(seeds, comps_at)]
R["components_build_total_s"] = time.perf_counter() - t0

# ==== SECTION 2: product machine (8 x 20 bits = 160 bits) =========================
P = {}
ats = comps_at; K = len(ats)
starts = [[int(v) for v in rng.integers(0, N, K)] for _ in range(300)]
fmis = 0; T_list = [12345, 10 ** 18, 2 ** 89 + 7, 10 ** 30 + 3]
for xs in starts:
    brs = [brent(a.fl, x) for a, x in zip(ats, xs)]
    for T in T_list:
        fmis += sum(a.fwd(x, T) != o1_state(b, T) for a, x, b in zip(ats, xs, brs))
P["forward_check"] = dict(product_states=len(starts), horizons=[str(t) for t in T_list], component_mismatches=int(fmis))
t0 = time.perf_counter()
for xs in starts:
    [a.fwd(x, 10 ** 30 + 3) for a, x in zip(ats, xs)]
P["forward_query_us"] = (time.perf_counter() - t0) / len(starts) * 1e6

def pick_target(a, x, achievable):
    if not achievable:
        return int(rng.integers(0, 256))
    return a.obsl[a.fwd(x, a.H + int(rng.integers(0, 10 ** 6)))]      # some value on x's own cycle

# (a) small joint queries: COMPLETE sieve verification (minimality and 'never')
agree = tried = hits = nevers = skipped = 0; pre = 0
while tried < 400:
    k = int(rng.integers(2, 5)); idx = sorted(rng.choice(K, k, replace=False).tolist())
    xs = [int(rng.integers(0, N)) for _ in idx]; sub = [ats[i] for i in idx]
    ys = [pick_target(a, x, rng.random() < 0.8) for a, x in zip(sub, xs)]
    brs = [brent(a.fl, x) for a, x in zip(sub, xs)]
    sv, bound = sieve_first([a.obs for a in sub], brs, ys)
    if sv == "skip":
        skipped += 1; continue
    tried += 1
    ta, info = joint_atlas(sub, xs, ys)
    agree += int(ta == sv); hits += int(sv is not None); nevers += int(sv is None); pre += int(info["regime"] == "pre-periodic")
P["joint_small_sieve_verified"] = dict(queries=tried, agree=agree, first_hits=hits, proved_never=nevers,
                                       pre_periodic_answers=pre, skipped_bound_over_3e7=skipped)

# (b) full 8-component joint queries (2^160 states): soundness by oracle, cross-check by Brent-derived residues
# Independent per-component targets. Expected solutions per joint period ~ L * prod(|R_i| / lam_i).
rows = []; qt = []; dens = []
for _ in range(200):
    xs = [int(rng.integers(0, N)) for _ in range(K)]; ys = [pick_target(a, x, True) for a, x in zip(ats, xs)]
    cr = [a.residues(x, y) for a, x, y in zip(ats, xs, ys)]
    dens.append(float(np.sum([np.log10(len(r[2]) / r[1]) for r in cr])))
    t0 = time.perf_counter(); ta, info = joint_atlas(ats, xs, ys); qt.append(time.perf_counter() - t0)
    brs = [brent(a.fl, x) for a, x in zip(ats, xs)]
    tb, _ = joint_brent(brs, [a.obsl for a in ats], ys)
    sound = None if ta is None else all(a.obsl[o1_state(b, ta)] == y for a, b, y in zip(ats, brs, ys))
    rows.append(dict(t=None if ta is None else str(ta), L=str(info.get("L")), peak=info.get("peak"),
                     regime=info["regime"], reason=info.get("reason"), brent_agrees=(ta == tb), sound=sound))
hit_t = [int(r["t"]) for r in rows if r["t"] is not None]
P["joint_full"] = dict(queries=len(rows), first_hits=len(hit_t), proved_never=sum(r["t"] is None for r in rows),
                       all_sound=all(r["sound"] for r in rows if r["sound"] is not None),
                       brent_residue_crosscheck_agree=sum(r["brent_agrees"] for r in rows),
                       log10_t_min=float(log10(min(hit_t))) if hit_t else None,
                       log10_t_median=float(np.median([log10(v) for v in hit_t])) if hit_t else None,
                       log10_t_max=float(log10(max(hit_t))) if hit_t else None,
                       max_residue_classes=max(r["peak"] for r in rows),
                       query_ms_median=float(np.median(qt) * 1e3), query_ms_max=float(max(qt) * 1e3),
                       never_reasons=sorted({r["reason"].split(" when")[0].split(" component")[0] for r in rows if r["reason"]}),
                       log10_hit_density_median=float(np.median(dens)),
                       log10_L_median=float(np.median([log10(int(r["L"])) for r in rows if r["L"] not in ("None",)])),
                       examples=rows[:5])

# (c) realizable joint targets: the 8 targets are what the machine actually shows at a far time T*.
# "When did this exact joint observation FIRST occur?"  Answer must be sound and <= T*.
rows = []; qt = []
for _ in range(200):
    xs = [int(rng.integers(0, N)) for _ in range(K)]
    Tstar = int(10 ** rng.uniform(12, 30))
    ys = [a.obsl[a.fwd(x, Tstar)] for a, x in zip(ats, xs)]
    t0 = time.perf_counter(); ta, info = joint_atlas(ats, xs, ys); qt.append(time.perf_counter() - t0)
    brs = [brent(a.fl, x) for a, x in zip(ats, xs)]
    tb, _ = joint_brent(brs, [a.obsl for a in ats], ys)
    sound = ta is not None and all(a.obsl[o1_state(b, ta)] == y for a, b, y in zip(ats, brs, ys))
    rows.append(dict(Tstar=Tstar, t=ta, L=info.get("L"), sound=sound, le_Tstar=(ta is not None and ta <= Tstar),
                     brent_agrees=(ta == tb), classes=info.get("classes")))
tt = [r["t"] for r in rows]
P["joint_realizable"] = dict(queries=len(rows), all_found=all(t is not None for t in tt), all_sound=all(r["sound"] for r in rows),
                             all_le_Tstar=all(r["le_Tstar"] for r in rows), brent_crosscheck_agree=sum(r["brent_agrees"] for r in rows),
                             first_occurrence_equals_Tstar=sum(r["t"] == r["Tstar"] for r in rows),
                             log10_Tstar_median=float(np.median([log10(r["Tstar"]) for r in rows])),
                             log10_first_median=float(np.median([log10(max(r["t"], 1)) for r in rows])),
                             log10_first_max=float(max(log10(max(r["t"], 1)) for r in rows)),
                             log10_L_median=float(np.median([log10(r["L"]) for r in rows if r["L"]])),
                             max_final_classes=max((r["classes"] or 0) for r in rows),
                             query_ms_median=float(np.median(qt) * 1e3), query_ms_max=float(max(qt) * 1e3),
                             examples=[dict(Tstar=str(r["Tstar"]), first=str(r["t"]), L=str(r["L"])) for r in rows[:6]])
s = ats[0].fl; x = 0; t0 = time.perf_counter()
for _ in range(200000):
    x = s[x]
P["table_step_ns_per_component"] = (time.perf_counter() - t0) / 200000 * 1e9
P["atlas_entries_used"] = K * N; P["state_space_log2"] = K * BITS
R["product"] = P

# ==== SECTION 3: cascade (sender -> receiver through a 4-bit port), 2^40 states ====
C = {}
drv_seed = 1010
DA = comps_at[seeds.index(drv_seed)]; fAl = DA.fl
del ats; comps_at = [DA]   # free the other component atlases
sym = AR & 15                                             # the sender emits the low nibble of its A register
t0 = time.perf_counter()
def build_G(seed):
    prog = make_program(seed, with_input=True); Gm = np.empty((16, N), np.int32)
    for u in range(16):
        Gm[u] = run_program(prog, AR, u)
    return Gm
def holonomy_on(Gm, c):
    lam = DA.lensl[c]; st = DA.order[DA.startsl[c]: DA.startsl[c] + lam]; sy = st & 15; Fm = np.arange(N, dtype=np.int32)
    for k in range(lam):
        Fm = Gm[sy[k]][Fm]
    return Fm
# Selection rule fixed in advance: first receiver seed >= 5000 whose holonomy over the sender's longest
# cycle keeps a receiver cycle of length >= 50 (i.e. the receiver is NOT entrained by the sender).
c_long = int(np.argmax(DA.lensl)); rcv_seed = 5000
while True:
    G = build_G(rcv_seed); Ft = holonomy_on(G, c_long); At = Atlas(Ft, OBS); ok = max(At.lensl) >= 50; del Ft, At
    if ok:
        break
    del G; rcv_seed += 1
C["port_table_s"] = time.perf_counter() - t0
HOL, hol_info = [], []
t0 = time.perf_counter()
for c in range(len(DA.lensl)):
    lam = DA.lensl[c]; cyc_states = DA.order[DA.startsl[c]: DA.startsl[c] + lam]; syms = sym[cyc_states]
    p = min(d for d in range(1, lam + 1) if lam % d == 0 and np.array_equal(syms, np.roll(syms, -d)))
    Fp = np.arange(N, dtype=np.int32)
    for k in range(p):
        Fp = G[syms[k]][Fp]                               # what p sender ticks do to every receiver state
    F = fpow(Fp, lam // p)
    HA = Atlas(F, OBS); HOL.append((F, HA))
    hol_info.append(dict(sender_cycle=lam, symbol_period=p, image_size_after_one_period=int(len(np.unique(F))), receiver_holonomy_cycles=len(HA.lensl),
                         holonomy_longest_cycle=max(HA.lensl), holonomy_max_tail=HA.H,
                         joint_eventual_period_max=lam * max(HA.lensl)))
C["holonomy_build_s"] = time.perf_counter() - t0
C["sender"] = dict(seed=drv_seed, cycles=DA.lensl, max_tail=DA.H); C["receiver_seed"] = rcv_seed; C["holonomies"] = hol_info

def cnav(a, b, t):
    hA = DA.hl[a]; k = t if t < hA else hA
    for _ in range(k):
        a, b = fAl[a], int(G[a & 15, b])
    t -= k
    if t == 0:
        return a, b
    c = DA.cidl[a]; lam = DA.lensl[c]; d = (lam - DA.posl[a]) % lam; d = t if t < d else d
    for _ in range(d):
        a, b = fAl[a], int(G[a & 15, b])
    t -= d
    if t == 0:
        return a, b
    m, r = divmod(t, lam)
    b = HOL[c][1].fwd(b, m)                               # m whole sender periods in one look
    for _ in range(r):
        a, b = fAl[a], int(G[a & 15, b])
    return a, b

# V1: brute-force joint iteration
nS, T = 4096, 120_000
aa = rng.integers(0, N, nS); bb = rng.integers(0, N, nS); a0, b0 = aa.copy(), bb.copy()
chk = sorted(set(rng.integers(0, T, 30).tolist()) | {0, 1, DA.H, DA.H + 1, T - 1})
fA_np = DA.f.astype(np.int64); mis = 0; t0 = time.perf_counter(); ci = 0
for t in range(T):
    if ci < len(chk) and t == chk[ci]:
        mis += sum(cnav(int(a0[j]), int(b0[j]), t) != (int(aa[j]), int(bb[j])) for j in range(100)); ci += 1
    bb = G[aa & 15, bb]; aa = fA_np[aa]
C["V1_bruteforce"] = dict(starts=nS, steps=T, checked_queries=100 * len(chk), mismatches=int(mis), seconds=time.perf_counter() - t0)

# V2: full receiver layer at astronomically large t: atlas jump vs independent repeated squaring
V2 = {}
for T2 in [10 ** 18, 2 ** 61 - 1]:
    ok = True
    for c, (F, HA) in enumerate(HOL):
        m = T2 // DA.lensl[c]
        ok &= bool(np.array_equal(HA.fwd_vec(AR, m), fpow(F, m)))
    V2[str(T2)] = ok
C["V2_full_layer_all_2^20_receiver_states_per_sender_cycle"] = V2

# V3: semigroup consistency at arbitrary phases
bad = 0
for _ in range(300):
    a, b = int(rng.integers(0, N)), int(rng.integers(0, N))
    t1, t2 = int(rng.integers(10 ** 17, 10 ** 18)), int(rng.integers(10 ** 17, 10 ** 18))
    bad += int(cnav(*cnav(a, b, t1), t2) != cnav(a, b, t1 + t2))
C["V3_semigroup_mismatches"] = bad

qs = [(int(rng.integers(0, N)), int(rng.integers(0, N))) for _ in range(2000)]
t0 = time.perf_counter()
for a, b in qs:
    cnav(a, b, 10 ** 18)
C["query_ms_t1e18"] = (time.perf_counter() - t0) / len(qs) * 1e3
a, b = qs[0]; t0 = time.perf_counter()
for _ in range(100000):
    a, b = fAl[a], int(G[a & 15, b])
C["joint_step_ns"] = (time.perf_counter() - t0) / 100000 * 1e9
C["iterate_1e18_years"] = 10 ** 18 * C["joint_step_ns"] * 1e-9 / 3.15576e7
C["flat_atlas_bytes_needed"] = (1 << 40) * 4 * 5
C["holonomy_bytes_used"] = G.nbytes + DA.f.nbytes * 5 + sum(F.nbytes * 6 for F, _ in HOL)
# Contrast: an ENTRAINED receiver (seed 5001). One sender period erases its memory.
del HOL
G2 = build_G(5001); F2 = holonomy_on(G2, c_long); A2 = Atlas(F2, OBS)
C["entrained_contrast_seed_5001"] = dict(image_size_after_one_period=int(len(np.unique(F2))),
                                         holonomy_cycles=len(A2.lensl), longest_cycle=max(A2.lensl), max_tail=A2.H)
del G2, F2, A2
# Structure of the holonomy: how much does one sender period ERASE, and is the rest reversible?
def holonomy_structure(seed):
    Gm = build_G(seed); res = []
    for c in range(len(DA.lensl)):
        Fm = holonomy_on(Gm, c); img = np.unique(Fm); Fi = Fm[img]
        res.append(dict(sender_cycle=DA.lensl[c], image=int(len(img)), bits_erased_once=float(np.log2(N / len(img))),
                        bijective_on_image=bool(np.array_equal(np.unique(Fi), img)),
                        idempotent=bool(np.array_equal(Fm[Fm], Fm))))
        del Fm, img, Fi
    del Gm
    return res
C["holonomy_structure"] = {str(rcv_seed): holonomy_structure(rcv_seed), "5001": holonomy_structure(5001)}
R["cascade"] = C

# ==== SECTION 4: admission budget for holonomy (negative control) ===================
# Holonomy cost = (period of the PERCEIVED symbol stream) x |receiver| element-steps.
budget = 2e10
def lcm_all(v):
    L = 1
    for x in v:
        L = L * x // gcd(L, x)
    return L
big = [max(c['cycles']) for c in R['components'][:3]]
Lp = lcm_all(big)
R["admission"] = dict(
    budget_element_steps=budget,
    case_receiver_reads_one_sender=dict(period=big[0], cost=big[0] * N, admitted=big[0] * N <= budget),
    case_receiver_reads_xor_of_three_senders=dict(state_period_bound=Lp, cost_bound=Lp * N, admitted=Lp * N <= budget,
        note="the XOR stream's minimal period divides this lcm; it is not computed, so admission is refused, not guessed"),
    case_flat_joint_atlas_2pow40=dict(cost=1 << 40, memory_bytes=(1 << 40) * 20, admitted=False))

json.dump(R, open(os.path.join(HERE, "results_ckn2.json"), "w"), indent=1, default=str)
print(json.dumps(R, indent=1, default=str))
