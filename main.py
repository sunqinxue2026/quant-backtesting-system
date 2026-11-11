from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

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
from quant_system.visualization.plots import plot_drawdown, plot_equity, plot_price_signals, plot_strategy_vs_benchmark


def main() -> None:
    parser = argparse.ArgumentParser(description="运行单股票双均线回测")
    parser.add_argument("csv", nargs="?", help="行情 CSV 文件；省略时运行 synthetic/test 演示")
    parser.add_argument("--output", default=None, help="报告输出目录")
    parser.add_argument("--short", type=int, default=None)
    parser.add_argument("--long", type=int, default=None)
    args = parser.parse_args()
    demo = args.csv is None
    csv_path = Path(args.csv) if not demo else PROJECT_ROOT / "data/test/synthetic_cycle_demo.csv"
    if not csv_path.is_absolute():
        csv_path = PROJECT_ROOT / csv_path
    if not csv_path.is_file():
        parser.error(f"行情 CSV 文件不存在: {csv_path}")
    args.short = args.short if args.short is not None else (2 if demo else 5)
    args.long = args.long if args.long is not None else (3 if demo else 20)
    if not 0 < args.short < args.long:
        parser.error("均线参数必须满足 0 < short < long")
    output = Path(args.output) if args.output else Path("reports/cycle_demo" if demo else "reports")
    if not output.is_absolute():
        output = PROJECT_ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    if demo:
        print("运行 synthetic/test 合成数据演示；结果不代表真实市场收益。")
    source = CsvMarketDataSource().load(csv_path, is_synthetic=demo)
    cleaned, quality = MarketDataCleaner().clean(source)
    enriched = add_indicators(cleaned, args.short, args.long)
    signals = DualMovingAverageStrategy(args.short, args.long).generate_signals(enriched)
    result = BacktestEngine(Portfolio(1_000_000)).run(enriched, signals)
    metrics = PerformanceAnalyzer().analyze(result.snapshots, result.trades)
    quality_payload = quality.to_dict()
    quality_payload["strategy_parameters"] = {"short_window": args.short, "long_window": args.long}
    quality_payload["cost_parameters"] = {"commission_rate": 0.0003, "min_commission": 0.0, "stamp_tax_rate": 0.0005, "slippage_bps": 10.0, "lot_size": 100}
    (output / "quality_report.json").write_text(json.dumps(quality_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    result.snapshots["drawdown"] = result.snapshots["total_value"] / result.snapshots["total_value"].cummax() - 1
    result.snapshots.to_csv(output / "account_snapshots.csv", index=False)
    if result.orders:
        (output / "orders.json").write_text(json.dumps([o.__dict__ for o in result.orders], ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    plot_equity(result.snapshots, output / "equity_curve.png")
    plot_drawdown(result.snapshots, output / "drawdown_curve.png")
    plot_price_signals(enriched, signals, output / "price_signals.png")
    plot_strategy_vs_benchmark(result.snapshots, enriched.set_index("trade_date")["close"], output / "strategy_vs_benchmark.png")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    print("回测完成：已生成绩效指标、质量报告、账户快照和四类 PNG 图表。")


if __name__ == "__main__":
    main()
