"""Step 2: build a single-node PyPSA network of Zambia's power system for one scenario.

Components
  - one bus for the whole country (no transmission constraints)
  - hydro reservoirs (Kariba North Bank, Kafue cascade) as storage units with an annual water budget
  - run-of-river hydro, existing solar, coal and HFO/diesel as generators
  - imports and load shedding as expensive "generators" that close the balance
  - in the expansion scenario: new solar and 4-hour batteries the optimiser may build
"""
from pathlib import Path

import pandas as pd
import pypsa
import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_config():
    with open(ROOT / "config.yaml") as f:
        return yaml.safe_load(f)


def load_costs(cfg):
    """Read PyPSA technology-data and return a helper to look up values."""
    costs = pd.read_csv(ROOT / cfg["economics"]["costs_file"])
    costs = costs.set_index(["technology", "parameter"])["value"]
    return lambda tech, param: float(costs.loc[(tech, param)])


def annuity(rate, lifetime):
    """Share of an investment paid back each year over the lifetime."""
    return rate / (1 - (1 + rate) ** -lifetime)


def annualised_cost(cost, tech, rate):
    """EUR per MW per year: investment annuity plus fixed O&M (technology-data gives EUR/kW)."""
    inv = cost(tech, "investment") * 1000
    return inv * (annuity(rate, cost(tech, "lifetime")) + cost(tech, "FOM") / 100)


def build_network(cfg, scenario):
    sc = cfg["scenarios"][scenario]
    hydrology = sc["hydrology"]
    cost = load_costs(cfg)
    rate = cfg["economics"]["discount_rate"]

    ts = pd.read_csv(ROOT / "resources" / "timeseries.csv", index_col=0, parse_dates=True)

    n = pypsa.Network(name=f"Zambia {scenario}")
    n.set_snapshots(ts.index)

    for carrier in ["AC", "hydro", "run-of-river", "solar", "coal", "hfo", "imports", "exports",
                    "load shedding", "battery"]:
        n.add("Carrier", carrier)

    n.add("Bus", "Zambia", carrier="AC")
    n.add("Load", "demand", bus="Zambia", p_set=ts["load_mw"])

    # Hydro reservoirs: inflow = annual water budget spread evenly; large storage lets the
    # optimiser decide when to use the water (cyclic: end the year where it started).
    for name, h in cfg["hydro_reservoirs"].items():
        n.add("StorageUnit", name, bus="Zambia", carrier="hydro",
              p_nom=h["p_nom_mw"], max_hours=8760, p_min_pu=0,
              inflow=h["budget_mw"][hydrology], cyclic_state_of_charge=True,
              efficiency_dispatch=1.0, marginal_cost=0.0)

    ror = cfg["run_of_river"]
    n.add("Generator", "run-of-river", bus="Zambia", carrier="run-of-river",
          p_nom=ror["p_nom_mw"], p_max_pu=ror["capacity_factor"][hydrology], marginal_cost=0.0)

    n.add("Generator", "solar", bus="Zambia", carrier="solar",
          p_nom=cfg["solar"]["p_nom_mw"], p_max_pu=ts["solar_pu"], marginal_cost=0.0)

    # Thermal: marginal cost = fuel / efficiency + variable O&M (technology-data)
    for name, tech in [("coal", "coal"), ("hfo", "oil")]:
        t = cfg["thermal"][name]
        mc = cost(tech, "fuel") / cost(tech, "efficiency") + cost(tech, "VOM")
        n.add("Generator", name, bus="Zambia", carrier=name, p_nom=t["p_nom_mw"],
              p_max_pu=t["availability"], marginal_cost=mc)

    imp = cfg["imports"]
    n.add("Generator", "imports", bus="Zambia", carrier="imports",
          p_nom=imp["p_nom_mw"], marginal_cost=imp["price_eur_mwh"])

    # Exports: a "generator" that can only run backwards (negative output). Its marginal cost
    # times a negative output is negative, so every MWh exported earns the export price.
    if sc["exports"]:
        exp = cfg["exports"]
        n.add("Generator", "exports", bus="Zambia", carrier="exports", p_nom=exp["p_nom_mw"],
              p_min_pu=-1, p_max_pu=0, marginal_cost=exp["price_eur_mwh"])

    # Load shedding in tiers: each block of shortfall costs a bit more than the one before
    ls = cfg["load_shedding"]
    block = cfg["demand"]["peak_mw"] / ls["tiers"]
    for k in range(ls["tiers"]):
        n.add("Generator", f"load shedding {k + 1}", bus="Zambia", carrier="load shedding",
              p_nom=block, marginal_cost=ls["voll_eur_mwh"] + k * ls["tier_step_eur_mwh"])

    if sc["expand"]:
        ex = cfg["expansion"]
        n.add("Generator", "solar (new)", bus="Zambia", carrier="solar",
              p_nom_extendable=True, p_nom_max=ex["solar_max_mw"], p_max_pu=ts["solar_pu"],
              capital_cost=annualised_cost(cost, "solar-utility", rate), marginal_cost=0.0)

        hours = ex["battery_hours"]
        eff = cost("battery inverter", "efficiency")
        battery_cc = (annualised_cost(cost, "battery inverter", rate)
                      + hours * cost("battery storage", "investment") * 1000
                      * annuity(rate, cost("battery storage", "lifetime")))
        n.add("StorageUnit", "battery (new)", bus="Zambia", carrier="battery",
              p_nom_extendable=True, p_nom_max=ex["battery_max_mw"], max_hours=hours,
              efficiency_store=eff, efficiency_dispatch=eff, cyclic_state_of_charge=True,
              capital_cost=battery_cc, marginal_cost=0.5)   # small wear cost per MWh discharged

    return n


if __name__ == "__main__":
    cfg = load_config()
    for scenario in cfg["scenarios"]:
        n = build_network(cfg, scenario)
        print(scenario, len(n.snapshots), "snapshots,", len(n.generators), "generators,",
              len(n.storage_units), "storage units")
