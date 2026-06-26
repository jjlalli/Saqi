import numpy as np
import matplotlib.pyplot as plt
import saqi
from saqi import Field, naive, cloud, saqi as saqi_strat, run, DAYS

saqi.ROUNDS = 80          # small components mix fast


def edges(grid):
    es = []   # unique undirected links
    nb = saqi.make_neighbours(grid)
    for u in nb:
        for v in nb[u]:
            if u < v:
                es.append((u, v))
    return es


def random_cut(grid, frac, rng):
    es = edges(grid)
    k = int(round(frac * len(es)))
    down = rng.choice(len(es), size=k, replace=False)
    cut = set()
    for j in down:
        u, v = es[j]
        cut.add((u, v)); cut.add((v, u))     # link is down both ways
    return cut


def survival(grid, frac, strat, seeds):
    out = []
    for s in seeds:
        saqi.SEED = s
        rng = np.random.default_rng(s)
        f = Field(np.random.default_rng(s), grid)
        cut = random_cut(grid, frac, rng)
        out.append(run(f, strat, cut)[-1] / (grid * grid))   # fraction alive
    return np.array(out)


def resilience():
    grid = 6
    fracs = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7]
    seeds = range(18)
    names = [("Naive timer", naive), ("Cloud (central)", cloud), ("Saqi (mesh)", saqi_strat)]
    plt.figure(figsize=(7, 4.2))
    for name, strat in names:
        m = [survival(grid, p, strat, seeds).mean() for p in fracs]
        plt.plot([100 * p for p in fracs], [100 * x for x in m], marker="o", linewidth=2, label=name)
        print(name, [round(100 * x) for x in m])
    plt.xlabel("Radio links down (%)")
    plt.ylabel("Grove still alive at season end (%)")
    plt.title("When the network breaks, the cloud loses what it can't reach")
    plt.ylim(0, 100)
    plt.legend()
    plt.tight_layout()
    plt.savefig("saqi_resilience.png", dpi=130)
    print("saved saqi_resilience.png")


def scaling():
    grids = [4, 6, 8, 10]
    p = 0.55                        # past the ~50% point where the lattice fragments
    seeds = range(12)
    plt.figure(figsize=(7, 4.2))
    colour = {"Cloud (central)": "#ff7f0e", "Saqi (mesh)": "#2ca02c"}
    for name, strat in [("Cloud (central)", cloud), ("Saqi (mesh)", saqi_strat)]:
        m = [survival(g, p, strat, seeds).mean() for g in grids]
        plt.plot([g * g for g in grids], [100 * x for x in m], marker="o", linewidth=2, label=name, color=colour[name])
        print(name, [round(100 * x) for x in m])
    plt.xlabel("Grove size (number of zones)")
    plt.ylabel("Grove alive at 55% links down (%)")
    plt.title("Bigger groves fragment, so centralizing gets worse at scale")
    plt.ylim(0, 100)
    plt.legend()
    plt.tight_layout()
    plt.savefig("saqi_scaling.png", dpi=130)
    print("saved saqi_scaling.png")


if __name__ == "__main__":
    print("resilience:")
    resilience()
    print("\nscaling:")
    scaling()
