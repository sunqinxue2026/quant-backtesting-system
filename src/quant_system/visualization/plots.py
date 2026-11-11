from __future__ import annotations

from pathlib import Path
import matplotlib.pyplot as plt
import pandas as pd


def plot_equity(snapshots: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(pd.to_datetime(snapshots["trade_date"]), snapshots["total_value"], label="Strategy equity")
    ax.set(title="Account Equity Curve", xlabel="Trade date", ylabel="Account value")
    ax.legend(); ax.grid(alpha=0.3); fig.tight_layout(); fig.savefig(output, dpi=150); plt.close(fig)


def plot_drawdown(snapshots: pd.DataFrame, output: str | Path) -> None:
    values = snapshots["total_value"].astype(float)
    drawdown = values / values.cummax() - 1
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.fill_between(pd.to_datetime(snapshots["trade_date"]), drawdown, 0, alpha=0.35, color="red")
    ax.set(title="Drawdown Curve", xlabel="Trade date", ylabel="Drawdown")
    ax.grid(alpha=0.3); fig.tight_layout(); fig.savefig(output, dpi=150); plt.close(fig)


def plot_price_signals(data: pd.DataFrame, signals: pd.DataFrame, output: str | Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 5)); dates = pd.to_datetime(data["trade_date"])
    ax.plot(dates, data["close"], label="Close")
    if "sma_short" in data: ax.plot(dates, data["sma_short"], label="SMA short")
    if "sma_long" in data: ax.plot(dates, data["sma_long"], label="SMA long")
    for side, marker, color in [("BUY", "^", "green"), ("SELL", "v", "red")]:
        subset = signals[signals["side"] == side]
        ax.scatter(pd.to_datetime(subset["trade_date"]), subset["sma_short"], marker=marker, color=color, label=side)
    ax.set(title="Price and Dual Moving Average Signals", xlabel="Trade date", ylabel="Price")
    ax.legend(); ax.grid(alpha=0.3); fig.tight_layout(); fig.savefig(output, dpi=150); plt.close(fig)


def plot_strategy_vs_benchmark(snapshots: pd.DataFrame, benchmark: pd.Series, output: str | Path) -> None:
    dates = pd.to_datetime(snapshots["trade_date"])
    strategy = snapshots["total_value"].astype(float) / float(snapshots["total_value"].iloc[0])
    base = benchmark.astype(float) / float(benchmark.iloc[0])
    fig, ax = plt.subplots(figsize=(10, 5)); ax.plot(dates, strategy, label="Strategy")
    ax.plot(dates, base.to_numpy(), label="Benchmark")
    ax.set(title="Strategy vs Benchmark", xlabel="Trade date", ylabel="Normalized value")
    ax.legend(); ax.grid(alpha=0.3); fig.tight_layout(); fig.savefig(output, dpi=150); plt.close(fig)
