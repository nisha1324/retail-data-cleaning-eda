"""Audit and clean the UCI Online Retail dataset.

Reads data/raw/Online Retail.xlsx, applies each cleaning rule in order while
logging how many rows (and how much revenue) it touches, and writes:

  data/clean/sales.csv          product sale lines (the analysis table)
  data/clean/returns.csv        cancelled invoice lines (InvoiceNo starts with "C")
  data/clean/non_product.csv    postage, fees, manual adjustments, samples ...
  results/data_quality_report.md  the before/after audit and the cleaning log
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw" / "Online Retail.xlsx"
CLEAN_DIR = ROOT / "data" / "clean"
RESULTS_DIR = ROOT / "results"

# Real products use a 5-digit stock code, optionally followed by letters
# (colour/size variants such as 84952C). Everything else is a service line.
PRODUCT_CODE = r"^\d{5}[A-Za-z]*$"
COUNTRY_FIXES = {"EIRE": "Ireland", "RSA": "South Africa", "USA": "United States"}


def load_raw() -> pd.DataFrame:
    return pd.read_excel(RAW, dtype={"InvoiceNo": str, "StockCode": str})


def audit(df: pd.DataFrame) -> pd.DataFrame:
    """One row per data-quality check on the raw file."""
    inv = df["InvoiceNo"]
    checks = {
        "Rows": len(df),
        "Missing CustomerID": df["CustomerID"].isna().sum(),
        "Missing Description": df["Description"].isna().sum(),
        "Exact duplicate rows": df.duplicated().sum(),
        "Cancellation lines (InvoiceNo 'C…')": inv.str.startswith("C").sum(),
        "Bad-debt adjustments (InvoiceNo 'A…')": inv.str.startswith("A").sum(),
        "Non-product stock codes": (~df["StockCode"].str.match(PRODUCT_CODE)).sum(),
        "Quantity <= 0": (df["Quantity"] <= 0).sum(),
        "UnitPrice <= 0": (df["UnitPrice"] <= 0).sum(),
        "Country = 'Unspecified'": (df["Country"] == "Unspecified").sum(),
    }
    out = pd.DataFrame({"check": checks.keys(), "rows": checks.values()})
    out["share_of_rows"] = (out["rows"] / len(df)).map("{:.2%}".format)
    return out


class CleaningLog:
    def __init__(self) -> None:
        self.steps: list[dict] = []

    def record(self, step: str, before: pd.DataFrame, after: pd.DataFrame) -> None:
        gross = lambda d: (d["Quantity"] * d["UnitPrice"]).sum()
        self.steps.append({
            "step": step,
            "rows_removed": len(before) - len(after),
            "rows_left": len(after),
            "value_removed_gbp": round(gross(before) - gross(after), 2),
        })

    def frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.steps)


def clean(raw: pd.DataFrame):
    log = CleaningLog()
    df = raw.copy()

    # 1. Tidy text fields first so duplicates that differ only by whitespace match.
    df["Description"] = df["Description"].str.strip()
    df["StockCode"] = df["StockCode"].str.strip().str.upper()
    df["Country"] = df["Country"].replace(COUNTRY_FIXES)

    step = df.drop_duplicates()
    log.record("Drop exact duplicate rows", df, step)
    df = step

    # 2. Cancellations are real business events: keep them, but in their own table.
    is_cancel = df["InvoiceNo"].str.startswith("C")
    returns = df[is_cancel].copy()
    step = df[~is_cancel]
    log.record("Move cancellation lines to returns table", df, step)
    df = step

    # 3. Bad-debt write-offs are accounting entries, not sales.
    step = df[~df["InvoiceNo"].str.startswith("A")]
    log.record("Drop bad-debt adjustments (InvoiceNo 'A…')", df, step)
    df = step

    # 4. Postage, bank/Amazon fees, manual lines, samples, gift vouchers.
    is_product = df["StockCode"].str.match(PRODUCT_CODE)
    non_product = df[~is_product].copy()
    step = df[is_product]
    log.record("Move non-product lines (postage, fees, manual…)", df, step)
    df = step

    # 5. Negative/zero quantities outside cancellations are stock write-offs
    #    ("damaged", "lost", "?"), almost all with price 0 and no customer.
    step = df[df["Quantity"] > 0]
    log.record("Drop non-cancellation lines with Quantity <= 0", df, step)
    df = step

    # 6. Zero-price lines are free samples or data-entry gaps: no revenue signal.
    step = df[df["UnitPrice"] > 0]
    log.record("Drop lines with UnitPrice <= 0", df, step)
    df = step

    df = df.copy()
    # Fill any remaining blank descriptions from the most common one for that code.
    common_desc = (raw.dropna(subset=["Description"])
                   .assign(StockCode=lambda d: d["StockCode"].str.strip().str.upper())
                   .groupby("StockCode")["Description"]
                   .agg(lambda s: s.str.strip().mode().iat[0]))
    df["Description"] = df["Description"].fillna(df["StockCode"].map(common_desc))

    # Guest checkouts have no CustomerID. Keep their revenue, but flag them so
    # customer-level analysis can exclude them.
    df["IsGuest"] = df["CustomerID"].isna()
    for frame in (df, returns, non_product):
        frame["CustomerID"] = frame["CustomerID"].astype("Int64")

    df["Revenue"] = (df["Quantity"] * df["UnitPrice"]).round(2)
    df["InvoiceMonth"] = df["InvoiceDate"].dt.to_period("M").astype(str)
    df["Weekday"] = df["InvoiceDate"].dt.day_name()
    df["Hour"] = df["InvoiceDate"].dt.hour
    returns["Revenue"] = (returns["Quantity"] * returns["UnitPrice"]).round(2)

    return df, returns, non_product, log.frame()


def summary(sales: pd.DataFrame, returns: pd.DataFrame) -> pd.DataFrame:
    rows = {
        "Sale lines": len(sales),
        "Invoices": sales["InvoiceNo"].nunique(),
        "Products (stock codes)": sales["StockCode"].nunique(),
        "Identified customers": sales["CustomerID"].nunique(),
        "Countries": sales["Country"].nunique(),
        "Period": f"{sales['InvoiceDate'].min():%Y-%m-%d} to {sales['InvoiceDate'].max():%Y-%m-%d}",
        "Gross product revenue (GBP)": f"{sales['Revenue'].sum():,.0f}",
        "Share of revenue from guest checkouts": f"{sales.loc[sales['IsGuest'], 'Revenue'].sum() / sales['Revenue'].sum():.1%}",
        "Cancelled value (GBP)": f"{-returns['Revenue'].sum():,.0f}",
        "Missing values left in sales (excl. guest CustomerID)":
            int(sales.drop(columns="CustomerID").isna().sum().sum()),
    }
    return pd.DataFrame({"metric": rows.keys(), "value": [str(v) for v in rows.values()]})


def write_report(audit_df, log_df, summary_df) -> Path:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / "data_quality_report.md"
    parts = [
        "# Data quality report\n",
        "_Generated by `scripts/clean_data.py`. Do not edit by hand._\n",
        "## 1. Raw data audit\n",
        "Checks overlap, so the rows don't add up to the total.\n",
        audit_df.to_markdown(index=False),
        "\n## 2. Cleaning log (rules applied in order)\n",
        "`value_removed_gbp` is Quantity x UnitPrice of the rows each step removed "
        "(negative for cancellations and write-offs).\n",
        log_df.to_markdown(index=False, floatfmt=",.2f"),
        "\n## 3. Clean sales table\n",
        summary_df.to_markdown(index=False),
        "",
    ]
    path.write_text("\n".join(parts))
    return path


def main() -> None:
    raw = load_raw()
    audit_df = audit(raw)
    sales, returns, non_product, log_df = clean(raw)
    summary_df = summary(sales, returns)

    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    sales.to_csv(CLEAN_DIR / "sales.csv", index=False)
    returns.to_csv(CLEAN_DIR / "returns.csv", index=False)
    non_product.to_csv(CLEAN_DIR / "non_product.csv", index=False)
    report = write_report(audit_df, log_df, summary_df)

    print(audit_df.to_string(index=False), "\n")
    print(log_df.to_string(index=False), "\n")
    print(summary_df.to_string(index=False))
    print(f"\nWrote {report.relative_to(ROOT)} and data/clean/*.csv")


if __name__ == "__main__":
    main()
