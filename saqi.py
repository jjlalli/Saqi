import numpy as np
import matplotlib.pyplot as plt

GRID = 6
DAYS = 60
SAFE = 0.20
DEATH_DAYS = 8        # olives can sit ~a week bone-dry before a zone is lost
ET0 = 0.06
RAIN_P = 0.06
ROUNDS = 200
SEED = 7


def make_neighbours(n):
    nb = {i: [] for i in range(n * n)}
    for r in range(n):
        for c in range(n):
            i = r * n + c
            if r > 0:      nb[i].append((r - 1) * n + c)
            if r < n - 1:  nb[i].append((r + 1) * n + c)
            if c > 0:      nb[i].append(i - 1)
            if c < n - 1:  nb[i].append(i + 1)
    return nb


class Field:
    def __init__(self, rng, grid=GRID):
        self.grid = grid
        self.n = grid * grid
        self.nb = make_neighbours(grid)
        self.moist = rng.uniform(0.35, 0.7, self.n)
        self.exposure = rng.uniform(0.85, 1.25, self.n)   # some zones dry faster
        self.alive = np.ones(self.n, dtype=bool)
        self.dry_streak = np.zeros(self.n, dtype=int)
        self.rng = rng

    def copy(self):
        f = Field.__new__(Field)
        f.grid, f.n, f.nb = self.grid, self.n, self.nb
        f.moist = self.moist.copy()
        f.exposure = self.exposure.copy()
        f.alive = self.alive.copy()
        f.dry_streak = self.dry_streak.copy()
        f.rng = np.random.default_rng(SEED)   # same weather for every strategy
        return f

    def day(self, allocate, cut=None):
        live = np.where(self.alive)[0]
        self.moist = np.minimum(self.moist + allocate(self, live, cut), 1.0)

        heat = 1.0 + 0.6 * self.rng.random()
        self.moist = np.maximum(self.moist - ET0 * heat * self.exposure, 0.0)
        if self.rng.random() < RAIN_P:
            self.moist = np.minimum(self.moist + self.rng.uniform(0.2, 0.5), 1.0)

        bone_dry = self.moist < 0.02
        self.dry_streak[bone_dry] += 1
        self.dry_streak[~bone_dry] = 0
        gone = self.alive & (self.dry_streak >= DEATH_DAYS)
        self.alive[gone] = False
        self.moist[~self.alive] = 0.0

    def budget(self):
        return 0.6 * (ET0 * 1.3 * self.exposure.mean()) * self.n   # ~60% of daily loss


def naive(field, live, cut=None):
    w = np.zeros(field.n)
    if len(live):
        w[live] = field.budget() / len(live)
    return np.minimum(w, 1.0 - field.moist)


def cloud(field, live, cut=None):
    # one gateway waters the driest first up to SAFE. it can only act on the
    # component it sits in, so anything cut off from it gets nothing.
    cut = cut or set()
    comps = components(field, live, cut)
    reach = max(comps, key=len) if comps else live
    w = np.zeros(field.n)
    rem = field.budget()
    for node in reach[np.argsort(field.moist[reach])]:
        if field.moist[node] >= SAFE:
            break
        give = min(SAFE - field.moist[node], rem)
        w[node] = give
        rem -= give
        if rem <= 1e-9:
            break
    return w


def saqi(field, live, cut=None):
    cut = cut or set()
    w = np.zeros(field.n)
    B = field.budget()
    for comp in components(field, live, cut):
        share = B * len(comp) / len(live)
        avg = consensus(field, comp, cut)
        T = gossip_cutoff(field.moist[comp], avg, len(comp), share)
        rescue = comp[field.moist[comp] < T]
        rem = share
        for node in rescue[np.argsort(field.moist[rescue])]:
            give = min(SAFE - field.moist[node], rem)
            w[node] = give
            rem -= give
            if rem <= 1e-9:
                break
    return w


def cutoff(moist, B):
    lo, hi = 0.0, SAFE
    for _ in range(40):
        T = 0.5 * (lo + hi)
        if np.where(moist < T, SAFE - moist, 0.0).sum() > B:
            hi = T
        else:
            lo = T
    return 0.5 * (lo + hi)


def gossip_cutoff(moist, avg, size, share):
    # same idea as cutoff(), but no node sees the whole field: estimate the
    # total rescue cost from the gossiped average, then bisect. everyone gets
    # the same T, so there's no coordinator.
    lo, hi = 0.0, SAFE
    for _ in range(30):
        T = 0.5 * (lo + hi)
        demand = np.where(moist < T, SAFE - moist, 0.0)
        total = (avg @ demand).mean() * size
        if total > share:
            hi = T
        else:
            lo = T
    return 0.5 * (lo + hi)


def consensus(field, comp, cut, rounds=None):
    # Metropolis-weighted averaging matrix. W**rounds @ x makes every node hold
    # the mean of x over its component, from neighbour exchanges alone.
    rounds = ROUNDS if rounds is None else rounds
    pos = {node: j for j, node in enumerate(comp)}
    deg = {node: sum(1 for k in field.nb[node]
                     if k in pos and (node, k) not in cut and (k, node) not in cut)
           for node in comp}
    L = len(comp)
    W = np.zeros((L, L))
    for node in comp:
        for k in field.nb[node]:
            if k in pos and (node, k) not in cut and (k, node) not in cut:
                W[pos[node], pos[k]] = 1.0 / (1 + max(deg[node], deg[k]))
        W[pos[node], pos[node]] = 1.0 - W[pos[node]].sum()
    return np.linalg.matrix_power(W, rounds)


def components(field, live, cut=None):
    cut = cut or set()
    liveset = set(live.tolist())
    seen, comps = set(), []
    for s in live:
        if s in seen:
            continue
        stack, comp = [s], []
        while stack:
            u = stack.pop()
            if u in seen:
                continue
            seen.add(u); comp.append(u)
            for v in field.nb[u]:
                if v in liveset and v not in seen and (u, v) not in cut and (v, u) not in cut:
                    stack.append(v)
        comps.append(np.array(comp))
    return comps


def run(field, allocate, cut=None):
    curve = []
    for _ in range(DAYS):
        field.day(allocate, cut)
        curve.append(int(field.alive.sum()))
    return curve


def many_seasons(strat, seeds):
    curves = []
    for s in seeds:
        global SEED
        SEED = s
        base = Field(np.random.default_rng(s))
        curves.append(run(base.copy(), strat))
    return np.array(curves)


if __name__ == "__main__":
    seeds = range(40)
    strategies = [("Naive timer", naive), ("Cloud (central)", cloud), ("Saqi (mesh)", saqi)]

    plt.figure(figsize=(7, 4.2))
    days = range(1, DAYS + 1)
    for name, strat in strategies:
        c = many_seasons(strat, seeds)
        mean, sd = c.mean(0), c.std(0)
        plt.plot(days, mean, label=name, linewidth=2)
        plt.fill_between(days, mean - sd, mean + sd, alpha=0.15)
        print(f"{name:18s} alive after {DAYS} days: {mean[-1]:.1f} +/- {sd[-1]:.1f} / {GRID*GRID}")

    plt.xlabel("Day of dry season")
    plt.ylabel("Olive zones still alive")
    plt.title("Keeping the grove alive on a scarce water budget (40 seasons)")
    plt.ylim(0, GRID * GRID + 1)
    plt.legend()
    plt.tight_layout()
    plt.savefig("saqi_demo.png", dpi=130)
    print("saved saqi_demo.png")
