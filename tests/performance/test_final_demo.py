"""最终入口契约：真实标记仅用于合成测试夹具，不作为真实市场证据。"""
import importlib.util
import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import select, func
from quant_system.database import create_session_factory, DataImportBatch, BacktestTask

spec = importlib.util.spec_from_file_location('final_demo', Path(__file__).parents[2]/'scripts'/'run_final_demo.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def inputs(tmp_path):
    source = Path(__file__).parents[2]/'data'/'test'/'synthetic_pipeline_demo.csv'
    csv = tmp_path/'synthetic_contract_fixture.csv'
    csv.write_bytes(source.read_bytes())
    meta = dict(source='synthetic/test-contract-only', symbol='000001.SZ',
        data_as_of='2024-01-12', price_type='未复权', is_synthetic=False,
        units=dict(price='CNY',volume='股',amount='CNY'),
        csv_sha256=hashlib.sha256(csv.read_bytes()).hexdigest(),
        limitations=['合成测试夹具，false仅覆盖真实入口契约，不代表真实行情'])
    path=tmp_path/'provenance.json'
    path.write_text(json.dumps(meta,ensure_ascii=False),encoding='utf-8')
    return csv,path


def test_repeat_reuses_batch_creates_new_task_and_keeps_report(tmp_path):
    csv,meta=inputs(tmp_path)
    factory=create_session_factory(f"sqlite:///{tmp_path/'demo.db'}")
    try:
        first=module.run_demo(csv,meta,factory,tmp_path/'first',short=2,long=3)
        before=(tmp_path/'first'/'task_1'/'report.json').read_bytes()
        second=module.run_demo(csv,meta,factory,tmp_path/'second',short=2,long=3)
        assert first['batch_id']==second['batch_id']
        assert not first['reused_batch'] and second['reused_batch']
        assert first['task_id'] != second['task_id']
        assert first['database_readback']==second['database_readback']=='passed'
        assert first['snapshots']==second['snapshots']==9
        assert first['metrics']==second['metrics']
        assert before==(tmp_path/'first'/'task_1'/'report.json').read_bytes()
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(DataImportBatch))==1
            assert session.scalar(select(func.count()).select_from(BacktestTask))==2
    finally:
        factory.kw['bind'].dispose()


def test_changed_csv_rejected_before_import(tmp_path):
    csv,meta=inputs(tmp_path)
    csv.write_bytes(csv.read_bytes()+b'\n')
    factory=create_session_factory(f"sqlite:///{tmp_path/'changed.db'}")
    try:
        with pytest.raises(ValueError,match='摘要'):
            module.run_demo(csv,meta,factory,tmp_path/'output')
        with factory() as session:
            assert session.scalar(select(func.count()).select_from(DataImportBatch))==0
    finally:
        factory.kw['bind'].dispose()


@pytest.mark.parametrize('expected,actual,equal', [
    ({'v': 0.0020232239778528918}, {'v': 0.002023223977852892}, True),
    ({'v': -0.9142294451192037}, {'v': -0.9142294451192036}, True),
    ({'v': 9700.0}, {'v': 9700.01}, False),
    ({'v': 1}, {'v': True}, False),
    ({'v': [1, 2]}, {'v': [1]}, False),
    ({'v': None}, {'other': None}, False),
])
def test_mysql_json_serialization_tolerance_is_strict(expected, actual, equal):
    assert module.report_values_equal(expected, actual) is equal
