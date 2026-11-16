"""Step 3: solve each scenario with the HiGHS solver and save results.

Outputs
  results/networks/<scenario>.nc   solved PyPSA networks (open with pypsa.Network(path))
  results/summary.csv              one row per scenario with the headline numbers
"""
from pathlib import Path

import pandas as pd

from build_network import ROOT, build_network, load_config


def summarise(n, scenario):
    p = n.generators_t.p
    gen = p.T.groupby(n.generators.carrier).sum().T.sum() / 1e6                     # TWh
    hydro_twh = n.storage_units_t.p.clip(lower=0)[list(n.storage_units.index[
        n.storage_units.carrier == "hydro"])].sum().sum() / 1e6
    shed = p.loc[:, n.generators.carrier == "load shedding"].sum(axis=1)

    solar = n.generators.index[n.generators.carrier == "solar"]
    available = (n.generators_t.p_max_pu[solar] * n.generators.p_nom_opt[solar]).sum().sum()
    curtailed = (available - p[solar].sum().sum()) / 1e6

    return {
        "scenario": scenario,
        "demand_TWh": n.loads_t.p_set.sum().sum() / 1e6,
        "hydro_reservoir_TWh": hydro_twh,
        "run_of_river_TWh": gen.get("run-of-river", 0.0),
        "solar_TWh": gen.get("solar", 0.0),
        "coal_TWh": gen.get("coal", 0.0),
        "hfo_TWh": gen.get("hfo", 0.0),
        "imports_TWh": gen.get("imports", 0.0),
        "exports_TWh": -gen.get("exports", 0.0),
        "unserved_TWh": shed.sum() / 1e6,
        "hours_with_shedding": int((shed > 1).sum()),
        "max_shortfall_MW": max(shed.max(), 0.0),
        "new_solar_MW": n.generators.p_nom_opt.get("solar (new)", 0.0),
        "new_battery_MW": n.storage_units.p_nom_opt.get("battery (new)", 0.0),
        "solar_curtailed_TWh": max(curtailed, 0.0),
        # Objective = operating costs + annualised new investment - export revenue
        "net_cost_MEUR": n.objective / 1e6,
    }


def main():
    cfg = load_config()
    out_dir = ROOT / "results" / "networks"
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for scenario in cfg["scenarios"]:
        n = build_network(cfg, scenario)
        status, condition = n.optimize(solver_name="highs", log_to_console=False)
        if status != "ok":
            raise RuntimeError(f"{scenario}: solver returned {status} ({condition})")
        n.export_to_netcdf(out_dir / f"{scenario}.nc")
        rows.append(summarise(n, scenario))
        print(f"solved {scenario}")
    summary = pd.DataFrame(rows).set_index("scenario").round(3) + 0.0   # + 0.0 turns -0.0 into 0.0
    summary["hours_with_shedding"] = summary["hours_with_shedding"].astype(int)
    summary.to_csv(ROOT / "results" / "summary.csv")
    print(summary.T.to_string())


if __name__ == "__main__":
    main()
