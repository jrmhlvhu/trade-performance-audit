#!/usr/bin/env python3
"""
Trade Performance Audit
=======================

Reads a cTrader "deals" statement (CSV) and asks one honest question:
is my profit coming from a repeatable edge, or from a few lucky trades?

What it does
  1. Loads the statement and cleans it up.
  2. Computes core performance numbers (win rate, payoff, profit factor, expectancy).
  3. Robustness tests: what happens if the best deals are removed? (and a bootstrap)
  4. Breaks results down by asset class.
  5. Saves three charts and a results.md report.

Usage
    python audit.py path/to/statement.csv --out outputs
"""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw charts to files, no window needed
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Chart colours (one validated palette: blue = main series / gains,
# orange = comparison series, red = losses; grey for chrome)
# ---------------------------------------------------------------------------
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
MUTED = "#898781"
GRID = "#e1e0d9"
BASELINE = "#c3c2b7"
BLUE = "#2a78d6"
ORANGE = "#eb6834"
RED = "#e34948"

# ---------------------------------------------------------------------------
# Asset classes (simple lookup; anything unknown is treated as FX)
# ---------------------------------------------------------------------------
INDICES = {"US500", "US30", "NAS100", "JPN225", "GER40", "FRA40", "UK100", "EU50", "AUS200", "HK50"}
METALS = {"XAUUSD", "XAGUSD", "XPTUSD", "XPDUSD", "COPPER"}
ENERGY = {"XTIUSD", "XBRUSD", "USOIL", "UKOIL", "WTI", "BRENT", "NGAS"}
CRYPTO_PREFIXES = ("BTC", "ETH", "LTC", "XRP", "SOL")


def classify(symbol: str) -> str:
    s = symbol.upper()
    if s in METALS:
        return "Metals"
    if s in ENERGY:
        return "Energy"
    if s.startswith(CRYPTO_PREFIXES):
        return "Crypto"
    if s in INDICES:
        return "Indices"
    return "FX"


def money(value: float, decimals: int = 0, signed: bool = True) -> str:
    """Format a number as money, e.g. +$232 or -$58."""
    if signed:
        sign = "+" if value > 0 else "−" if value < 0 else ""
    else:
        sign = "−" if value < 0 else ""
    return f"{sign}${abs(value):,.{decimals}f}"


# ---------------------------------------------------------------------------
# 1. Load the statement
# ---------------------------------------------------------------------------
def load_statement(path: str) -> pd.DataFrame:
    """Parse the cTrader statement. The file has a title line, a header row that
    starts with 'Symbol', the deals, then a totals row and a summary block."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        lines = f.read().splitlines()

    header_idx = next((i for i, line in enumerate(lines) if line.startswith("Symbol,")), None)
    if header_idx is None:
        raise SystemExit("Could not find the 'Symbol,...' header row. Is this a cTrader deals statement?")

    header = next(csv.reader([lines[header_idx]]))
    rows = []
    for line in lines[header_idx + 1:]:
        if not line.strip():
            break
        fields = next(csv.reader([line]))
        if not fields[0].strip():  # the totals row has an empty first column
            break
        rows.append(fields)

    df = pd.DataFrame(rows, columns=header).rename(
        columns={
            "Symbol": "symbol",
            "Opening Direction": "direction",
            "Closing Time (UTC+1)": "time",
            "Closing quantity": "quantity",
            "Net USD": "pnl",
            "Balance USD": "balance",
        }
    )
    df["time"] = pd.to_datetime(df["time"], format="%d %b %Y %H:%M:%S.%f")
    df["pnl"] = df["pnl"].astype(float)
    df["balance"] = df["balance"].astype(float)
    df = df.sort_values("time", kind="stable").reset_index(drop=True)
    df["asset_class"] = df["symbol"].map(classify)
    return df


# ---------------------------------------------------------------------------
# 2. Core performance numbers
# ---------------------------------------------------------------------------
def longest_losing_streak(pnl: pd.Series) -> int:
    best = run = 0
    for value in pnl:
        run = run + 1 if value < 0 else 0
        best = max(best, run)
    return best


def performance(df: pd.DataFrame) -> dict:
    p = df["pnl"]
    wins, losses = p[p > 0], p[p < 0]
    breakeven = int((p == 0).sum())

    # Max drawdown measured on cumulative deal P&L (in dollars, not % of equity)
    cum = np.concatenate([[0.0], p.cumsum().to_numpy()])
    max_dd = float((np.maximum.accumulate(cum) - cum).max())

    return {
        "deals": len(p),
        "net": float(p.sum()),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": breakeven,
        "win_rate_all": len(wins) / len(p),
        "win_rate_ex_flat": len(wins) / (len(wins) + len(losses)),
        "avg_win": float(wins.mean()),
        "avg_loss": float(losses.mean()),
        "payoff": float(wins.mean() / abs(losses.mean())),
        "profit_factor": float(wins.sum() / abs(losses.sum())),
        "expectancy": float(p.mean()),
        "median": float(p.median()),
        "best": float(p.max()),
        "worst": float(p.min()),
        "max_dd": max_dd,
        "losing_streak": longest_losing_streak(p),
    }


# ---------------------------------------------------------------------------
# 3. Robustness: does the edge survive without the best deals?
# ---------------------------------------------------------------------------
def robustness(df: pd.DataFrame, ns=(1, 3, 5)) -> pd.DataFrame:
    p = df["pnl"]
    net = p.sum()
    rows = []
    for n in ns:
        top = p.nlargest(n).sum()
        rows.append(
            {
                "removed": f"best {n}",
                "top_pnl": top,
                "net_without": net - top,
                "share_of_net": top / net if net > 0 else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def bootstrap_mean(p: pd.Series, n_boot: int = 10_000, seed: int = 42) -> dict:
    """Resample the deals with replacement many times and look at how much the
    average P&L per deal moves around. If the 95% range includes zero, the data
    cannot rule out that the true average is zero."""
    rng = np.random.default_rng(seed)
    arr = p.to_numpy()
    means = rng.choice(arr, size=(n_boot, len(arr)), replace=True).mean(axis=1)
    low, high = np.percentile(means, [2.5, 97.5])
    return {
        "mean": float(arr.mean()),
        "ci_low": float(low),
        "ci_high": float(high),
        "prob_le_zero": float((means <= 0).mean()),
        "n_boot": n_boot,
    }


# ---------------------------------------------------------------------------
# 4. Breakdowns
# ---------------------------------------------------------------------------
def by_asset_class(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("asset_class")["pnl"].agg(
        deals="size",
        net="sum",
        win_rate=lambda s: (s > 0).mean(),
        avg="mean",
    )
    return g.sort_values("net", ascending=False)


def balance_moves(df: pd.DataFrame, threshold: float = 5.0) -> pd.DataFrame:
    """Balance changes that closed-deal P&L does not explain (deposits,
    withdrawals, transfers, fees). This is why a % return cannot be read from
    this file alone."""
    bal = df["balance"].to_numpy()
    pnl = df["pnl"].to_numpy()
    diff = bal[1:] - bal[:-1] - pnl[1:]
    moves = pd.DataFrame({"time": df["time"].iloc[1:].to_numpy(), "amount": diff})
    return moves[moves["amount"].abs() >= threshold].reset_index(drop=True)


# ---------------------------------------------------------------------------
# 5. Charts
# ---------------------------------------------------------------------------
def style_axes(ax, grid_axis="y"):
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelsize=9, length=0)
    ax.grid(True, axis=grid_axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def add_titles(ax, title, subtitle):
    ax.set_title(title, loc="left", color=INK, fontsize=14, fontweight="bold", pad=34)
    # matplotlib treats a pair of $ signs as maths, so escape them
    ax.text(0, 1.04, subtitle.replace("$", r"\$"), transform=ax.transAxes, color=INK2, fontsize=10, va="bottom")


def money_axis(ax, axis="y"):
    fmt = plt.FuncFormatter(lambda v, _: money(v, signed=False))
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def date_range_text(df):
    return f"{df['time'].min():%d %b %Y} to {df['time'].max():%d %b %Y}"


def chart_cumulative(df, path):
    p = df["pnl"]
    top3 = p.nlargest(3).index
    p_without = p.copy()
    p_without[top3] = 0.0
    t = df["time"]
    cum_all, cum_wo = p.cumsum(), p_without.cumsum()

    fig, ax = plt.subplots(figsize=(10, 5.8), dpi=200, facecolor=SURFACE)
    style_axes(ax)
    ax.axhline(0, color=BASELINE, linewidth=1)
    ax.plot(t, cum_all, color=BLUE, linewidth=2, label="All deals")
    ax.plot(t, cum_wo, color=ORANGE, linewidth=2, label="Without the 3 best deals")

    # Mark the three best deals on the main line
    ax.scatter(t[top3], cum_all[top3], s=70, color=BLUE, edgecolor=SURFACE, linewidth=2, zorder=5)
    for idx in top3:
        ax.annotate(
            f"{df.at[idx, 'symbol']} {money(df.at[idx, 'pnl'])}",
            xy=(t[idx], cum_all[idx]),
            xytext=(-12, 0),
            textcoords="offset points",
            ha="right",
            va="center",
            color=INK2,
            fontsize=9,
        )

    # Direct labels at the right-hand end of each line
    for series, colour in ((cum_all, BLUE), (cum_wo, ORANGE)):
        ax.annotate(
            money(series.iloc[-1]),
            xy=(t.iloc[-1], series.iloc[-1]),
            xytext=(8, 0),
            textcoords="offset points",
            va="center",
            color=INK,
            fontsize=10,
            fontweight="bold",
        )

    ax.set_xlim(t.min(), t.max() + pd.Timedelta(days=10))
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    money_axis(ax)
    ax.legend(loc="upper left", frameon=False, labelcolor=INK2, fontsize=9)
    add_titles(ax, "Cumulative profit and loss, with and without the best deals",
               f"Closed deals, {date_range_text(df)}. USD. Balance deposits and withdrawals excluded.")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_ranked(df, path):
    order = df["pnl"].sort_values(ascending=False)
    values = order.to_numpy()
    symbols = df.loc[order.index, "symbol"].to_numpy()
    colours = [BLUE if v > 0 else RED if v < 0 else BASELINE for v in values]
    x = np.arange(1, len(values) + 1)
    top3 = values[:3].sum()
    rest = values.sum() - top3

    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=200, facecolor=SURFACE)
    style_axes(ax)
    ax.bar(x, values, color=colours, width=0.75)
    ax.axhline(0, color=BASELINE, linewidth=1)

    for i in range(3):
        ax.annotate(f"{symbols[i]} {money(values[i])}", xy=(x[i], values[i]), xytext=(8, 0),
                    textcoords="offset points", va="center", color=INK2, fontsize=9)
    ax.annotate(f"{symbols[-1]} {money(values[-1])}", xy=(x[-1], values[-1]), xytext=(-30, 0),
                textcoords="offset points", ha="right", va="center", color=INK2, fontsize=9)

    ax.set_xlim(0, len(values) + 1)
    ax.set_xlabel("Deals ranked from best to worst", color=MUTED, fontsize=9)
    money_axis(ax)
    verb = "lost" if rest < 0 else "made"
    add_titles(ax, "Deals ranked by profit and loss",
               f"The 3 best deals made {money(top3, signed=False)}. The other {len(values) - 3} deals combined {verb} {money(abs(rest), signed=False)}.")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


def chart_asset_class(df, path):
    g = df.groupby("asset_class")["pnl"].agg(["sum", "count"]).sort_values("sum")
    colours = [BLUE if v > 0 else RED for v in g["sum"]]
    labels = [f"{name} ({int(row['count'])} deals)" for name, row in g.iterrows()]

    fig, ax = plt.subplots(figsize=(10, 4.2), dpi=200, facecolor=SURFACE)
    style_axes(ax, grid_axis="x")
    ax.barh(labels, g["sum"], color=colours, height=0.55)
    ax.axvline(0, color=BASELINE, linewidth=1)
    span = max(abs(g["sum"].max()), abs(g["sum"].min()), 1)
    ax.set_xlim(g["sum"].min() - 0.22 * span if g["sum"].min() < 0 else -0.05 * span,
                g["sum"].max() + 0.22 * span)
    for y, v in enumerate(g["sum"]):
        ax.annotate(money(v), xy=(v, y), xytext=(6 if v >= 0 else -6, 0), textcoords="offset points",
                    ha="left" if v >= 0 else "right", va="center", color=INK, fontsize=10, fontweight="bold")
    ax.tick_params(axis="y", labelcolor=INK2, labelsize=10)
    money_axis(ax, axis="x")
    add_titles(ax, "Net profit and loss by asset class",
               f"Closed deals, {date_range_text(df)}. USD.")
    fig.tight_layout()
    fig.savefig(path, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------------------
# 6. Report
# ---------------------------------------------------------------------------
def build_report(df, perf, robust, boot, classes, moves) -> str:
    L = []
    L.append("# Trade Performance Audit - results\n")
    L.append(f"Statement period: {date_range_text(df)}  \nClosed deals analysed: {perf['deals']}\n")

    L.append("## Core numbers\n")
    L.append("| Metric | Value |\n|---|---|")
    L.append(f"| Net P&L | {money(perf['net'], 2)} |")
    L.append(f"| Winning / losing / breakeven deals | {perf['wins']} / {perf['losses']} / {perf['breakeven']} |")
    L.append(f"| Win rate (all deals) | {perf['win_rate_all']:.1%} |")
    L.append(f"| Win rate (excluding breakeven) | {perf['win_rate_ex_flat']:.1%} |")
    L.append(f"| Average win | {money(perf['avg_win'], 2)} |")
    L.append(f"| Average loss | {money(perf['avg_loss'], 2)} |")
    L.append(f"| Payoff ratio (average win / average loss) | {perf['payoff']:.2f} |")
    L.append(f"| Profit factor (gross profit / gross loss) | {perf['profit_factor']:.2f} |")
    L.append(f"| Expectancy per deal | {money(perf['expectancy'], 2)} |")
    L.append(f"| Median deal | {money(perf['median'], 2)} |")
    L.append(f"| Best / worst deal | {money(perf['best'], 2)} / {money(perf['worst'], 2)} |")
    L.append(f"| Max drawdown on cumulative P&L | {money(perf['max_dd'], 2, signed=False)} |")
    L.append(f"| Longest losing streak (deals) | {perf['losing_streak']} |\n")

    L.append("## Does the edge survive without the best deals?\n")
    L.append("| Removed | Their P&L | Net P&L without them | Share of total net |\n|---|---|---|---|")
    for _, r in robust.iterrows():
        share = "n/a" if pd.isna(r["share_of_net"]) else f"{r['share_of_net']:.0%}"
        L.append(f"| {r['removed']} | {money(r['top_pnl'], 2)} | {money(r['net_without'], 2)} | {share} |")
    L.append("")

    L.append("## Bootstrap: is the average deal really positive?\n")
    L.append(
        f"Resampled the {perf['deals']} deals {boot['n_boot']:,} times. Average P&L per deal: "
        f"{money(boot['mean'], 2)}. 95% range: {money(boot['ci_low'], 2)} to {money(boot['ci_high'], 2)}. "
        f"In {boot['prob_le_zero']:.1%} of resamples the average was zero or negative.\n"
    )
    if boot["ci_low"] <= 0:
        L.append("The 95% range includes zero, so this sample cannot rule out that the true average is zero. "
                 "More trades are needed.\n")

    L.append("## By asset class\n")
    L.append("| Asset class | Deals | Net P&L | Win rate | Average deal |\n|---|---|---|---|---|")
    for name, r in classes.iterrows():
        L.append(f"| {name} | {int(r['deals'])} | {money(r['net'], 2)} | {r['win_rate']:.0%} | {money(r['avg'], 2)} |")
    L.append("")

    L.append("## Balance changes not explained by deal P&L\n")
    if moves.empty:
        L.append("None found.\n")
    else:
        # Amounts are left out on purpose so results.md is safe to publish.
        L.append(f"{len(moves)} balance changes of 5 USD or more are not explained by closed-deal P&L "
                 "(likely deposits, withdrawals, transfers or fees). Because of these, a percentage "
                 "return cannot be computed from this file alone.\n")

    L.append("## Limits of this analysis\n")
    L.append("- The statement shows closing times only. It has no opening time and no stop-loss, so holding periods "
             "and risk per trade (R-multiples) cannot be measured here.\n"
             "- A position closed in parts appears as several deals, so counts and win rate are per deal, not per trade.\n"
             "- The sample is small, and deals are not fully independent (several can come from one idea).\n"
             "- Max drawdown here is in dollars on cumulative P&L, not a percentage of account equity.\n")
    return "\n".join(L)


# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Audit a cTrader deals statement.")
    parser.add_argument("statement", help="path to the statement CSV")
    parser.add_argument("--out", default="outputs", help="folder for charts and report")
    parser.add_argument("--boot", type=int, default=10_000, help="bootstrap resamples")
    parser.add_argument("--seed", type=int, default=42, help="random seed (for repeatable results)")
    args = parser.parse_args()

    df = load_statement(args.statement)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    perf = performance(df)
    robust = robustness(df)
    boot = bootstrap_mean(df["pnl"], args.boot, args.seed)
    classes = by_asset_class(df)
    moves = balance_moves(df)

    chart_cumulative(df, out / "cumulative_pnl.png")
    chart_ranked(df, out / "deals_ranked.png")
    chart_asset_class(df, out / "pnl_by_asset_class.png")

    report = build_report(df, perf, robust, boot, classes, moves)
    (out / "results.md").write_text(report, encoding="utf-8")
    print(report)
    print(f"\nSaved charts and results.md to {out.resolve()}")


if __name__ == "__main__":
    main()
