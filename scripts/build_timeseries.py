"""Step 1: build hourly demand and solar profiles for one year.

Outputs resources/timeseries.csv with columns:
  load_mw   hourly national demand in MW
  solar_pu  solar output per MW installed (0 to 1)
"""
from pathlib import Path

import numpy as np
import pandas as pd
import pvlib
import yaml

ROOT = Path(__file__).resolve().parents[1]


def hourly_index(cfg):
    year = cfg["year"]
    return pd.date_range(f"{year}-01-01 00:00", f"{year}-12-31 23:00", freq="h",
                         tz=cfg["timezone"])


def build_load(cfg, index):
    """Flat mining load plus a daily and seasonal shape for everyone else.

    The non-mining shape is scaled so the total hits the configured average and peak.
    """
    d = cfg["demand"]
    hour = index.hour.to_numpy()
    month = index.month.to_numpy()

    # Daily shape (unitless): low at night, morning ramp, evening peak around 19:00
    daily = np.array([0.55, 0.52, 0.50, 0.50, 0.52, 0.60, 0.75, 0.85, 0.88, 0.88, 0.87, 0.86,
                      0.85, 0.84, 0.84, 0.86, 0.90, 1.00, 1.15, 1.20, 1.10, 0.95, 0.80, 0.65])
    # Seasonal shape: cold season (June to August) adds heating and longer lighting hours
    seasonal = np.array([0.97, 0.97, 0.98, 1.00, 1.03, 1.07, 1.08, 1.05, 1.00, 0.98, 0.97, 0.96])
    shape = daily[hour] * seasonal[month - 1]

    mining = d["mining_share"] * d["average_mw"]
    # Solve rest = a + b * shape so that mean(total) = average and max(total) = peak
    target_mean = d["average_mw"] - mining
    target_max = d["peak_mw"] - mining
    b = (target_max - target_mean) / (shape.max() - shape.mean())
    a = target_mean - b * shape.mean()
    return mining + a + b * shape


def build_solar(cfg, index):
    """Clear-sky PV output, derated by a monthly cloud factor and scaled to the target capacity factor."""
    loc_cfg = cfg["location"]
    s = cfg["solar"]
    site = pvlib.location.Location(loc_cfg["lat"], loc_cfg["lon"], tz=cfg["timezone"],
                                   altitude=loc_cfg["altitude_m"])
    # Use mid-hour timestamps so the sun position represents each hour
    times = index + pd.Timedelta(minutes=30)
    sun = site.get_solarposition(times)
    clear = site.get_clearsky(times, model="haurwitz")           # GHI only
    split = pvlib.irradiance.erbs(clear["ghi"], sun["zenith"], times)
    poa = pvlib.irradiance.get_total_irradiance(
        surface_tilt=s["tilt_deg"], surface_azimuth=0,             # 0 = facing north
        solar_zenith=sun["apparent_zenith"], solar_azimuth=sun["azimuth"],
        dni=split["dni"], ghi=clear["ghi"], dhi=split["dhi"])["poa_global"].fillna(0)

    cloud = np.array(s["monthly_cloud_factor"])[index.month.to_numpy() - 1]
    raw = (poa.to_numpy() / 1000.0) * cloud
    scaled = raw * s["annual_cf"] / raw.mean()
    return np.clip(scaled, 0, 1)


def main():
    with open(ROOT / "config.yaml") as f:
        cfg = yaml.safe_load(f)
    index = hourly_index(cfg)
    ts = pd.DataFrame({"load_mw": build_load(cfg, index),
                       "solar_pu": build_solar(cfg, index)},
                      index=index.tz_localize(None))
    ts.index.name = "snapshot"
    out = ROOT / "resources" / "timeseries.csv"
    out.parent.mkdir(exist_ok=True)
    ts.round(4).to_csv(out)
    print(f"Wrote {out}")
    print(f"  demand: {ts.load_mw.sum() / 1e6:.2f} TWh, peak {ts.load_mw.max():.0f} MW, "
          f"min {ts.load_mw.min():.0f} MW")
    print(f"  solar capacity factor: {ts.solar_pu.mean():.3f}, max {ts.solar_pu.max():.2f}")


if __name__ == "__main__":
    main()
