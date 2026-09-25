"""Download the UCI Online Retail dataset (~23 MB xlsx) into data/raw/.

Source: Chen, D. (2015). Online Retail. UCI Machine Learning Repository.
https://doi.org/10.24432/C5BW33 (CC BY 4.0)
"""
import io
import urllib.request
import zipfile
from pathlib import Path

URL = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
TARGET = RAW_DIR / "Online Retail.xlsx"


def main() -> None:
    if TARGET.exists():
        print(f"Already downloaded: {TARGET}")
        return
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {URL} ...")
    with urllib.request.urlopen(URL, timeout=120) as resp:
        payload = resp.read()
    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        zf.extract("Online Retail.xlsx", RAW_DIR)
    print(f"Saved {TARGET} ({TARGET.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
