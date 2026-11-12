"""无界面PNG图表；不依赖交互桌面。"""
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager


def plot_report(curves, prices, signals, output, task_id, subtitle):
    """输出净值、回撤、价格信号、基准对比；文件名携带任务编号。"""
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    available = {f.name for f in font_manager.fontManager.ttflist}
    font = next((f for f in ('Microsoft YaHei','SimHei','Noto Sans CJK SC','DejaVu Sans') if f in available), 'DejaVu Sans')
    paths = []
    with plt.rc_context({'font.family':font, 'axes.unicode_minus':False}):
        for kind,title in [('equity','账户净值'),('drawdown','账户回撤'),('price_signals','价格、均线与信号'),('comparison','策略与基准累计收益')]:
            fig,ax = plt.subplots(figsize=(11,6))
            try:
                if kind == 'equity':
                    ax.plot(curves.trade_date, curves.normalized_equity, label='策略净值（初始资金=1）')
                    ax.set_ylabel('净值')
                elif kind == 'drawdown':
                    ax.fill_between(curves.trade_date, curves.drawdown * 100, 0, alpha=.4, label='回撤（包含初始资金峰值）')
                    ax.set_ylabel('回撤 %')
                elif kind == 'comparison':
                    ax.plot(curves.trade_date,(curves.normalized_equity-1)*100,label='策略（含实际配置成本）')
                    ax.plot(curves.trade_date,(curves.benchmark_equity-1)*100,label='基准（无成本收盘价买入持有）')
                    ax.set_ylabel('累计收益 %')
                else:
                    for col,label in [('close','收盘价'),('sma_short','短均线'),('sma_long','长均线')]:
                        ax.plot(prices.trade_date, prices[col],label=label)
                    for side,marker,color,label in [('BUY','^','red','买入信号'),('SELL','v','green','卖出信号')]:
                        subset = signals[signals.side == side]
                        selected = prices[prices.trade_date.isin(subset.signal_date)]
                        ax.scatter(selected.trade_date, selected.close, marker=marker,color=color,s=90,label=label,zorder=4)
                    ax.set_ylabel('价格 CNY')
                ax.set_title(f'任务{task_id} · {title}\n{subtitle}', fontsize=10)
                ax.set_xlabel('交易日期')
                ax.grid(alpha=.25)
                ax.legend(fontsize=8)
                fig.autofmt_xdate()
                fig.tight_layout()
                path = output / f'task_{task_id}_{kind}.png'
                fig.savefig(path,dpi=130)
                paths.append(path.name)
            finally:
                plt.close(fig)
    return paths
