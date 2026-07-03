import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# The watering control loop underneath the allocation: when to open and shut each valve.

THETA0   = 0.20     # start: thirsty
THETA_LO = 0.30     # below this a tree asks for water
THETA_HI = 0.55     # target root-zone moisture
THETA_MAX = 0.60    # field capacity: anything above this drains past the roots and is lost
Q        = 0.020    # inflow while the valve is open (per minute)
K        = 0.20     # how fast emitter water reaches the root zone (per minute)
DT       = 0.25     # minutes per step
NOISE    = 0.010    # sensor noise

ORANGE = "#d1662f"
GREEN  = "#2ca02c"
GREY   = "#888888"


def water_tree(mode, minutes=60, seed=0):
    # theta: root-zone moisture. p: water applied but not yet reached the roots.
    rng = np.random.default_rng(seed)
    theta, p, valve, lost = THETA0, 0.0, True, 0.0
    th, cm, vv = [], [], []
    steps = int(minutes / DT)
    for _ in range(steps):
        if valve:
            p += Q * DT
        flux = K * p * DT
        p -= flux
        theta += flux
        if theta > THETA_MAX:                        # excess drains below the root zone
            lost += theta - THETA_MAX
            theta = THETA_MAX

        if valve:
            if mode == "root":                       # stop when the slow sensor hits target
                signal = theta + rng.normal(0, NOISE)
            else:                                    # stop when committed water hits target
                signal = theta + p + rng.normal(0, NOISE)
            if signal >= THETA_HI:
                valve = False
        th.append(theta); cm.append(theta + p); vv.append(valve)
    return np.array(th), np.array(cm), np.array(vv), lost


def fig_stop():
    t = np.arange(0, 60, DT)
    th_n, cm_n, v_n, lost_n = water_tree("root")
    th_s, cm_s, v_s, lost_s = water_tree("committed")

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.2), sharey=True)

    for a, th, cm, vv, name, col, lost in [
        (ax[0], th_n, cm_n, v_n, "Stop on root-zone sensor", ORANGE, lost_n),
        (ax[1], th_s, cm_s, v_s, "Stop on committed water", GREEN, lost_s),
    ]:
        open_t = t[vv]
        if len(open_t):
            a.axvspan(open_t[0], open_t[-1], color=col, alpha=0.08, label="valve open")
        a.axhline(THETA_HI, color=GREY, ls="--", lw=1)
        a.axhline(THETA_MAX, color=GREY, ls=":", lw=1)
        a.plot(t, cm, color=col, lw=1.3, ls=":", label="committed (theta + in transit)")
        a.plot(t, th, color=col, lw=2.2, label="root-zone moisture")
        a.text(58, THETA_HI - 0.02, "target", ha="right", va="top", color=GREY, fontsize=9)
        a.text(58, THETA_MAX + 0.004, "field capacity", ha="right", va="bottom", color=GREY, fontsize=9)
        a.set_title(f"{name}\nsettles at {th[-1]:.2f}, drains away {lost:.2f}", fontsize=10)
        a.set_xlabel("minutes")
        a.legend(fontsize=8, loc="lower right")
    ax[0].set_ylabel("moisture")
    fig.suptitle("Same valve, two stop rules: the naive sensor keeps the valve open too long and overfills", fontsize=11)
    fig.tight_layout(rect=[0, 0, 1, 0.94])
    fig.savefig("saqi_control_stop.png", dpi=130)
    print(f"root-zone stop: settles {th_n[-1]:.3f}, drained {lost_n:.3f}")
    print(f"committed stop: settles {th_s[-1]:.3f}, drained {lost_s:.3f}")
    print("saved saqi_control_stop.png")


def run_cluster(mode, n=9, cap=2, minutes=240, seed=1):
    # one pump feeds only `cap` trees at once; a satisfied tree frees its slot.
    rng = np.random.default_rng(seed)
    theta = rng.uniform(0.22, 0.45, n)
    p = np.zeros(n)
    serving = np.zeros(n, bool)
    et = rng.uniform(0.0012, 0.0022, n)     # per-minute drying, per tree
    water, lost = 0.0, 0.0
    steps = int(minutes / DT)
    open_hist = np.zeros((steps, n), bool)

    for s in range(steps):
        committed = theta + p
        # free the pump for any tree that has reached target
        done = serving & (committed >= THETA_HI if mode == "committed" else theta >= THETA_HI)
        serving[done] = False
        # thirsty trees request; fill free pump slots, driest first
        thirsty = np.where((~serving) & (theta < THETA_LO))[0]
        free = cap - serving.sum()
        if free > 0 and len(thirsty):
            for node in thirsty[np.argsort(theta[thirsty])][:free]:
                serving[node] = True

        p[serving] += Q * DT
        water += Q * DT * serving.sum()
        flux = K * p * DT
        p -= flux
        theta += flux
        over = np.maximum(theta - THETA_MAX, 0.0)     # drains past the roots
        lost += over.sum()
        theta = np.minimum(theta, THETA_MAX)
        theta = np.maximum(theta - et * DT, 0.0)
        open_hist[s] = serving

    return water, lost, theta, open_hist


def fig_cluster():
    w_n, lost_n, th_n, hist_n = run_cluster("root")
    w_s, lost_s, th_s, hist_s = run_cluster("committed")
    t = np.arange(0, 240, DT)

    fig, ax = plt.subplots(1, 2, figsize=(10, 4.4), gridspec_kw={"width_ratios": [2, 1]})

    a = ax[0]
    for i in range(hist_s.shape[1]):
        on = hist_s[:, i]
        a.fill_between(t, i + 0.15, i + 0.85, where=on, color=GREEN, alpha=0.8, linewidth=0)
    a.set_yticks(range(hist_s.shape[1]))
    a.set_yticklabels([f"tree {i+1}" for i in range(hist_s.shape[1])], fontsize=8)
    a.set_xlabel("minutes")
    a.set_title("One pump, two at a time: valves take turns as trees finish", fontsize=10)

    b = ax[1]
    b.bar(["stop on\nroot sensor", "stop on\ncommitted"], [lost_n, lost_s], color=[ORANGE, GREEN])
    b.set_ylabel("water drained past the roots")
    drop = 100 * (lost_n - lost_s) / lost_n if lost_n else 0
    b.set_title(f"{drop:.0f}% less water wasted,\nsame trees kept in band", fontsize=10)
    for i, v in enumerate([lost_n, lost_s]):
        b.text(i, v, f"{v:.2f}", ha="center", va="bottom", fontsize=9)

    fig.tight_layout()
    fig.savefig("saqi_control_cluster.png", dpi=130)
    print(f"cluster waste: root-stop {lost_n:.2f} vs committed-stop {lost_s:.2f}")
    print("saved saqi_control_cluster.png")


if __name__ == "__main__":
    fig_stop()
    fig_cluster()
