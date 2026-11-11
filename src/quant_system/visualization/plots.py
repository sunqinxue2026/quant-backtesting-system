from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


def plot_equity(snapshots: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(pd.to_datetime(snapshots["trade_date"]), snapshots["total_value"], label="Equity")
    ax.set_title("Account Equity Curve")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(output, dpi=150); plt.close(fig)

def plot_price_signals(data: pd.DataFrame, signals: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    dates = pd.to_datetime(data["trade_date"])
    ax.plot(dates, data["close"], label="Close")
    if "sma_short" in data: ax.plot(dates, data["sma_short"], label="SMA short")
    if "sma_long" in data: ax.plot(dates, data["sma_long"], label="SMA long")
    for side, marker, color in [("BUY", "^", "green"), ("SELL", "v", "red")]:
        subset = signals[signals["side"] == side]
        ax.scatter(pd.to_datetime(subset["trade_date"]), subset["sma_short"], marker=marker, color=color, label=side)
    ax.set_title("Price and Dual Moving Average Signals")
    ax.legend(); ax.grid(alpha=0.3)
    fig.tight_layout(); fig.savefig(output, dpi=150); plt.close(fig)
