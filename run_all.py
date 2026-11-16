"""Run the whole model: data, profiles, scenarios, figures. Takes about three minutes."""
import subprocess
import sys
from pathlib import Path

STEPS = ["retrieve_costs.py", "build_timeseries.py", "solve_network.py", "make_figures.py"]
SCRIPTS = Path(__file__).resolve().parent / "scripts"

for step in STEPS:
    print(f"\n=== {step} ===", flush=True)
    subprocess.run([sys.executable, str(SCRIPTS / step)], check=True, cwd=SCRIPTS)
