"""第六阶段：从已保存任务生成绩效和PNG，不重新成交。"""
import argparse
import json
import os
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from quant_system.database import create_session_factory
from quant_system.performance import generate_report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task-id',type=int,required=True)
    parser.add_argument('--database',choices=['demo','configured'],default='demo')
    parser.add_argument('--output',type=Path,default=ROOT/'reports'/'stage6')
    parser.add_argument('--annualization-days',type=int,default=252)
    parser.add_argument('--risk-free-rate',type=float,default=0.0)
    args=parser.parse_args()
    if args.database=='configured':
        url=os.getenv('DATABASE_URL')
        if not url:
            parser.error('configured模式要求DATABASE_URL')
    else:
        db=ROOT/'reports'/'stage5_pipeline'/'demo.db'
        if not db.exists():
            parser.error('请先运行第五阶段完整链路演示')
        url=f'sqlite:///{db}'
    factory=None
    try:
        factory=create_session_factory(url)
        result=generate_report(factory,args.task_id,args.output,annualization_days=args.annualization_days,risk_free_rate=args.risk_free_rate)
        print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    except Exception as exc:
        print(f'绩效生成失败 type={type(exc).__name__}；文件与数据库不是同一事务，已生成文件可能保留。',file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        if factory is not None:
            factory.kw['bind'].dispose()

if __name__=='__main__':
    main()
