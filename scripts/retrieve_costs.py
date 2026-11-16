"""Step 0: download technology cost assumptions from PyPSA technology-data (pinned release)."""
import urllib.request

from build_network import ROOT, load_config


def main():
    cfg = load_config()["economics"]
    target = ROOT / cfg["costs_file"]
    if target.exists():
        print(f"{target} already present")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(cfg["costs_url"], target)
    print(f"Downloaded {cfg['costs_url']}")


if __name__ == "__main__":
    main()
