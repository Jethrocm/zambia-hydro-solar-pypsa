"""Step 4: draw the three result figures from the solved networks.

Outputs results/figures/
  1_energy_mix.png          annual supply by source in each scenario
  2_hydro_daily_profile.png average hydro output by hour of day (baseload vs balancer)
  3_drought_week.png        dispatch in the worst drought week, with and without new solar
"""
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import pypsa

from build_network import ROOT, load_config

FIG = ROOT / "results" / "figures"

# Colours from a colour-blind-checked palette; the stack order below keeps adjacent
# colours distinguishable for the common types of colour blindness.
STACK = ["hydro", "run-of-river", "battery", "coal", "hfo", "imports", "solar", "load shedding"]
COLOURS = {"hydro": "#2a78d6", "run-of-river": "#1baf7a", "battery": "#eb6834",
           "coal": "#6250d6", "hfo": "#e87ba4", "imports": "#008300", "solar": "#eda100",
           "load shedding": "#e34948", "exports": "#898781"}
LABELS = {"hydro": "Hydro reservoirs", "run-of-river": "Run-of-river hydro", "battery": "Battery",
          "coal": "Coal", "hfo": "HFO/diesel", "imports": "Imports", "solar": "Solar",
          "load shedding": "Unserved demand", "exports": "Exports"}
SCENARIO_LABELS = {"normal": "Normal year", "drought": "Drought year (2024-style)",
                   "drought_solar_storage": "Drought year + new solar and batteries"}
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#fcfcfb"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 10, "axes.edgecolor": "#c3c2b7",
    "axes.labelcolor": INK2, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE, "legend.frameon": False,
})


def dispatch_by_carrier(n):
    """Hourly MW by carrier. Storage discharge is positive, charging and exports negative."""
    gen = n.generators_t.p.T.groupby(n.generators.carrier).sum().T
    sto = n.storage_units_t.p.T.groupby(n.storage_units.carrier).sum().T
    return pd.concat([gen, sto], axis=1).fillna(0)


def title(fig, ax, main, sub):
    fig.suptitle(main, x=0.01, y=0.98, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.01, 0.90, sub, ha="left", fontsize=10, color=INK2)


def fig_energy_mix(networks):
    rows = {}
    for sc, n in networks.items():
        d = dispatch_by_carrier(n).sum() / 1e6
        rows[sc] = d
    df = pd.DataFrame(rows).T.fillna(0)
    supply = [c for c in STACK if c != "battery" and c in df]

    fig, ax = plt.subplots(figsize=(10, 4.2))
    names = list(networks)
    for i, sc in enumerate(names):
        left = 0.0
        for c in supply:
            v = max(df.loc[sc, c], 0)
            if v <= 0.001:
                continue
            ax.barh(i, v, left=left, color=COLOURS[c], height=0.55, edgecolor=SURFACE, linewidth=2)
            if v >= 0.9:
                ink = INK if c in ("solar", "run-of-river", "hfo") else "white"
                ax.text(left + v / 2, i, f"{v:.1f}", ha="center", va="center", fontsize=9, color=ink)
            left += v
        exp = -df.loc[sc].get("exports", 0)
        if exp > 0.001:
            ax.barh(i, -exp, color=COLOURS["exports"], height=0.55, edgecolor=SURFACE, linewidth=2)
            ax.text(-exp / 2, i, f"{exp:.1f}", ha="center", va="center", fontsize=9, color="white")

    ax.set_yticks(range(len(names)), [SCENARIO_LABELS[s] for s in names], color=INK)
    ax.invert_yaxis()
    ax.axvline(0, color="#c3c2b7", linewidth=1)
    ax.set_xlabel("TWh per year (exports shown left of zero)")
    ax.grid(axis="x", color=GRID, linewidth=0.6)
    ax.set_axisbelow(True)
    handles = [plt.Rectangle((0, 0), 1, 1, color=COLOURS[c]) for c in supply + ["exports"]
               if c in df and (df[c].abs() > 0.001).any()]
    labels = [LABELS[c] for c in supply + ["exports"] if c in df and (df[c].abs() > 0.001).any()]
    ax.legend(handles, labels, ncol=4, loc="upper center", bbox_to_anchor=(0.45, -0.22), fontsize=9)

    shed = df.loc["drought", "load shedding"]
    new_solar = networks["drought_solar_storage"].generators.p_nom_opt.get("solar (new)", 0) / 1000
    title(fig, ax, f"A 2024-style drought leaves {shed:.1f} TWh unserved; "
                   f"{new_solar:.1f} GW of new solar closes the gap",
          "TWh per year. Demand is 17.5 TWh in every scenario; supply above it is exported.")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.savefig(FIG / "1_energy_mix.png", dpi=150)
    plt.close(fig)


def fig_hydro_profile(networks):
    fig, ax = plt.subplots(figsize=(10, 4.4))
    colours = ["#2a78d6", "#eb6834", "#1baf7a"]        # first three palette slots
    for (sc, n), col in zip(networks.items(), colours):
        hydro = n.storage_units_t.p[n.storage_units.index[n.storage_units.carrier == "hydro"]].sum(axis=1)
        prof = hydro.groupby(hydro.index.hour).mean()
        ax.plot(prof.index, prof.values, color=col, linewidth=2, label=SCENARIO_LABELS[sc])
        short = {"normal": "Normal", "drought": "Drought", "drought_solar_storage": "Drought + solar"}[sc]
        ax.text(23.3, prof.values[-1], short, color=INK2, fontsize=9, va="center")
    ax.set_xlim(0, 23)
    ax.set_ylim(bottom=0)
    ax.set_xticks(range(0, 24, 3), [f"{h:02d}:00" for h in range(0, 24, 3)])
    ax.set_ylabel("Average hydro reservoir output, MW")
    ax.grid(axis="y", color=GRID, linewidth=0.6)
    ax.legend(loc="upper left", fontsize=9)
    title(fig, ax, "With more solar, hydro moves from baseload to evening balancer",
          "Kariba North Bank and Kafue cascade combined, averaged over the year by hour of day")
    fig.tight_layout(rect=(0, 0, 1, 0.88))
    fig.subplots_adjust(right=0.86)
    fig.savefig(FIG / "2_hydro_daily_profile.png", dpi=150)
    plt.close(fig)


def fig_drought_week(networks):
    drought = networks["drought"]
    shed = dispatch_by_carrier(drought)["load shedding"]
    worst_day = shed.resample("D").sum().idxmax()
    start = worst_day - pd.Timedelta(days=3)
    window = slice(start, start + pd.Timedelta(days=7) - pd.Timedelta(hours=1))

    pair = ["drought", "drought_solar_storage"]
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, sharey=True)
    for ax, sc in zip(axes, pair):
        d = dispatch_by_carrier(networks[sc]).loc[window]
        pos = [c for c in STACK if c in d and (d[c].clip(lower=0) > 0.5).any()]
        ax.stackplot(d.index, *[d[c].clip(lower=0) for c in pos],
                     colors=[COLOURS[c] for c in pos], labels=[LABELS[c] for c in pos],
                     edgecolor=SURFACE, linewidth=0.3)
        neg = {k: d[k].clip(upper=0) for k in ["battery", "exports"] if k in d and (d[k] < -0.5).any()}
        if neg:
            ax.stackplot(d.index, *neg.values(), colors=[COLOURS[k] for k in neg], alpha=0.55,
                         edgecolor=SURFACE, linewidth=0.3)
        demand = networks[sc].loads_t.p_set["demand"].loc[window]
        ax.plot(demand.index, demand.values, color=INK, linewidth=1.5, label="Demand")
        ax.set_title(SCENARIO_LABELS[sc], loc="left", fontsize=10, color=INK)
        ax.grid(axis="y", color=GRID, linewidth=0.6)
        ax.set_ylabel("MW")
        ax.axhline(0, color="#c3c2b7", linewidth=0.8)
    handles, labels = [], []
    for ax in axes:
        for h, l in zip(*ax.get_legend_handles_labels()):
            if l not in labels:
                handles.append(h)
                labels.append(l)
    axes[1].legend(handles, labels, ncol=5, loc="upper center", bbox_to_anchor=(0.5, -0.18), fontsize=9)
    axes[1].xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter("%a %d %b"))
    fig.suptitle("In the worst drought week, new solar carries the day; hydro and batteries the night",
                 x=0.01, ha="left", fontsize=13, fontweight="bold", color=INK)
    fig.text(0.01, 0.925, "Hourly dispatch in MW; the black line is demand. Below zero: battery charging.",
             fontsize=10, color=INK2)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(FIG / "3_drought_week.png", dpi=150)
    plt.close(fig)


def main():
    cfg = load_config()
    FIG.mkdir(parents=True, exist_ok=True)
    networks = {sc: pypsa.Network(ROOT / "results" / "networks" / f"{sc}.nc")
                for sc in cfg["scenarios"]}
    fig_energy_mix(networks)
    fig_hydro_profile(networks)
    fig_drought_week(networks)
    print(f"Figures written to {FIG}")


if __name__ == "__main__":
    main()
