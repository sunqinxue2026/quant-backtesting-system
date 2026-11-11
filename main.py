from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# 支持直接运行 main.py（包括 PyCharm 的“运行当前文件”配置）。
# 通过 pyproject.toml 安装项目或设置 PYTHONPATH 时不会产生副作用。
PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from quant_system.cleaning.cleaner import MarketDataCleaner
from quant_system.data.loader import CsvMarketDataSource
from quant_system.engine.backtest import BacktestEngine
from quant_system.engine.portfolio import Portfolio
from quant_system.indicators.technical import add_indicators
from quant_system.performance.analyzer import PerformanceAnalyzer
from quant_system.strategies.dual_ma import DualMovingAverageStrategy
from quant_system.visualization.plots import plot_equity, plot_price_signals


def main() -> None:
    parser = argparse.ArgumentParser(description="运行单股票双均线回测")
    parser.add_argument("csv", help="行情 CSV 文件")
    parser.add_argument("--output", default="reports", help="报告输出目录")
    parser.add_argument("--short", type=int, default=5)
    parser.add_argument("--long", type=int, default=20)
    args = parser.parse_args()
    output = Path(args.output); output.mkdir(parents=True, exist_ok=True)
    source = CsvMarketDataSource().load(args.csv)
    cleaned, quality = MarketDataCleaner().clean(source)
    enriched = add_indicators(cleaned, args.short, args.long)
    signals = DualMovingAverageStrategy(args.short, args.long).generate_signals(enriched)
    result = BacktestEngine(Portfolio(1_000_000)).run(enriched, signals)
    metrics = PerformanceAnalyzer().analyze(result.snapshots, result.trades)
    (output / "quality_report.json").write_text(json.dumps(quality.__dict__, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    plot_equity(result.snapshots, output / "equity_curve.png")
    plot_price_signals(enriched, signals, output / "price_signals.png")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
