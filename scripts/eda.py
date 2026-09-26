"""Exploratory analysis of the cleaned Online Retail sales.

Reads data/clean/sales.csv and data/clean/returns.csv (run clean_data.py first)
and writes charts to results/charts/ plus the numbers behind them to
results/eda_summary.md.

Revenue is reported NET of returns: product sale lines minus cancelled product
lines. Non-product returns (discounts, postage refunds, manual) are excluded,
matching how non-product sale lines were separated in cleaning.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = ROOT / "data" / "clean"
RESULTS_DIR = ROOT / "results"
CHART_DIR = RESULTS_DIR / "charts"

PRODUCT_CODE = r"^\d{5}[A-Za-z]*$"  # same rule as clean_data.py
LAST_FULL_MONTH = "2011-11"  # data stops on 2011-12-09
WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
BLUE, GREY, RED = "#2f6db5", "#b8bec6", "#c44e52"

plt.rcParams.update({
    "figure.dpi": 120, "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "axes.titlesize": 12, "font.size": 10,
})
gbp = mtick.FuncFormatter(lambda v, _: f"£{v / 1e3:,.0f}k")


def load():
    sales = pd.read_csv(CLEAN_DIR / "sales.csv", parse_dates=["InvoiceDate"],
                        dtype={"InvoiceNo": str, "StockCode": str})
    returns = pd.read_csv(CLEAN_DIR / "returns.csv", parse_dates=["InvoiceDate"],
                          dtype={"InvoiceNo": str, "StockCode": str})
    returns = returns[returns["StockCode"].str.match(PRODUCT_CODE)].copy()
    returns["InvoiceMonth"] = returns["InvoiceDate"].dt.to_period("M").astype(str)
    return sales, returns


def monthly(sales, returns):
    m = pd.DataFrame({
        "gross": sales.groupby("InvoiceMonth")["Revenue"].sum(),
        "returns": returns.groupby("InvoiceMonth")["Revenue"].sum(),
        "invoices": sales.groupby("InvoiceMonth")["InvoiceNo"].nunique(),
    }).fillna(0)
    m["net"] = m["gross"] + m["returns"]  # returns are negative
    m["avg_order_value"] = m["gross"] / m["invoices"]
    return m


def chart_monthly(m):
    full = m.loc[:LAST_FULL_MONTH]
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.bar(full.index, full["gross"], color=GREY, label="Gross sales")
    ax.bar(full.index, full["net"], color=BLUE, label="Net of returns")
    ax.yaxis.set_major_formatter(gbp)
    ax.set_title("Monthly product revenue (Dec 2010 – Nov 2011)")
    ax.tick_params(axis="x", rotation=45)
    ax.legend(frameon=False)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "01_monthly_revenue.png")
    plt.close(fig)


def chart_weekday_hour(sales):
    by_day = sales.groupby("Weekday")["Revenue"].sum().reindex(WEEKDAYS).fillna(0)
    by_hour = sales.groupby("Hour")["Revenue"].sum()
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.8))
    a1.bar([d[:3] for d in by_day.index], by_day, color=BLUE)
    a1.set_title("Revenue by weekday")
    a2.bar(by_hour.index, by_hour, color=BLUE)
    a2.set_title("Revenue by hour of order (UK time)")
    a2.set_xticks(by_hour.index)
    for a in (a1, a2):
        a.yaxis.set_major_formatter(gbp)
    fig.tight_layout()
    fig.savefig(CHART_DIR / "02_weekday_hour.png")
    plt.close(fig)
    return by_day, by_hour


def top_products(sales, returns, n=10):
    gross = sales.groupby("StockCode").agg(
        description=("Description", "first"), gross=("Revenue", "sum"),
        units=("Quantity", "sum"))
    gross["returns"] = returns.groupby("StockCode")["Revenue"].sum()
    gross["returns"] = gross["returns"].fillna(0)
    gross["net"] = gross["gross"] + gross["returns"]
    return gross.sort_values("net", ascending=False).head(n)


def chart_products(top):
    t = top.iloc[::-1]
    labels = [d.title()[:34] for d in t["description"]]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(labels, t["net"], color=BLUE)
    ax.xaxis.set_major_formatter(gbp)
    ax.set_title("Top 10 products by net revenue")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "03_top_products.png")
    plt.close(fig)


def countries(sales, returns):
    c = pd.DataFrame({
        "gross": sales.groupby("Country")["Revenue"].sum(),
        "returns": returns.groupby("Country")["Revenue"].sum(),
        "customers": sales.groupby("Country")["CustomerID"].nunique(),
    }).fillna(0)
    c["net"] = c["gross"] + c["returns"]
    c["share"] = c["net"] / c["net"].sum()
    return c.sort_values("net", ascending=False)


def chart_countries(c, n=10):
    intl = c.drop("United Kingdom").head(n).iloc[::-1]
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.barh(intl.index, intl["net"], color=BLUE)
    ax.xaxis.set_major_formatter(gbp)
    uk = c.loc["United Kingdom", "share"]
    ax.set_title(f"Top 10 markets outside the UK (UK itself = {uk:.0%} of net revenue)")
    fig.tight_layout()
    fig.savefig(CHART_DIR / "04_top_countries.png")
    plt.close(fig)


def fmt(df, money=(), pct=()):
    out = df.copy()
    for col in money:
        out[col] = out[col].map("£{:,.0f}".format)
    for col in pct:
        out[col] = out[col].map("{:.1%}".format)
    return out.to_markdown()


def main():
    CHART_DIR.mkdir(parents=True, exist_ok=True)
    sales, returns = load()

    m = monthly(sales, returns)
    chart_monthly(m)
    by_day, by_hour = chart_weekday_hour(sales)
    top = top_products(sales, returns)
    chart_products(top)
    c = countries(sales, returns)
    chart_countries(c)

    full = m.loc[:LAST_FULL_MONTH]
    q4 = full.loc["2011-09":"2011-11", "net"].sum()
    h1 = full.loc["2011-01":"2011-06", "net"].sum()
    gross, ret = sales["Revenue"].sum(), returns["Revenue"].sum()

    lines = [
        "# EDA summary (generated by scripts/eda.py)",
        "",
        "## Headline",
        f"- Gross product revenue: £{gross:,.0f}",
        f"- Product returns: −£{-ret:,.0f} ({-ret / gross:.1%} of gross)",
        f"- Net product revenue: £{gross + ret:,.0f}",
        f"- Sep–Nov 2011 net revenue: £{q4:,.0f} ({q4 / full['net'].sum():.1%} of the 12 full months)",
        f"- Jan–Jun 2011 net revenue: £{h1:,.0f}",
        f"- Best month: {full['net'].idxmax()} (£{full['net'].max():,.0f}); "
        f"weakest: {full['net'].idxmin()} (£{full['net'].min():,.0f})",
        f"- Saturday orders: {int((sales['Weekday'] == 'Saturday').sum())} lines",
        f"- Peak weekday: {by_day.idxmax()} (£{by_day.max():,.0f}); peak hour: {by_hour.idxmax()}:00 "
        f"(£{by_hour.max():,.0f})",
        f"- Orders placed 10:00–15:59: {by_hour.loc[10:15].sum() / by_hour.sum():.1%} of revenue",
        "",
        f"## Monthly (Dec 2011 is partial, data ends {sales['InvoiceDate'].max():%Y-%m-%d})",
        fmt(m.round(2), money=("gross", "returns", "net", "avg_order_value")),
        "",
        "## Top 10 products by net revenue",
        fmt(top, money=("gross", "returns", "net")),
        f"\nTop 10 products = {top['net'].sum() / (gross + ret):.1%} of net revenue "
        f"(out of {sales['StockCode'].nunique():,} products).",
        "",
        "## Top 10 countries by net revenue",
        fmt(c.head(10), money=("gross", "returns", "net"), pct=("share",)),
        "",
    ]
    (RESULTS_DIR / "eda_summary.md").write_text("\n".join(lines))
    print("\n".join(lines[:14]))


if __name__ == "__main__":
    main()
