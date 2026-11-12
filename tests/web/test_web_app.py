"""网页测试仅使用临时数据库，不写入用户演示库。"""
from pathlib import Path
from datetime import date
import pytest
from streamlit.testing.v1 import AppTest
from quant_system.database import create_session_factory, BacktestTask, BacktestResult
from quant_system.data import DataLoadRequest
from quant_system.data_import import import_csv
from sqlalchemy import select, func

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture
def app(tmp_path,monkeypatch):
    db=tmp_path/'web.db'
    monkeypatch.setenv('QUANT_WEB_DEMO_DB',str(db))
    factory=create_session_factory(f'sqlite:///{db.as_posix()}')
    import_csv(DataLoadRequest(ROOT/'data/test/synthetic_pipeline_demo.csv','synthetic/test','2024-01-12','未复权',{'price':'CNY','volume':'股','amount':'CNY'},True),factory)
    app=AppTest.from_file(str(ROOT/'web_app.py'),default_timeout=45)
    app.run()
    assert not app.exception
    yield app,factory
    factory.kw['bind'].dispose()

@pytest.mark.parametrize('page',['系统总览','数据管理','创建回测','任务与逐日回放','绩效与任务对比','使用教程'])
def test_pages_load(app,page):
    at,_=app
    at.sidebar.radio[0].set_value(page).run()
    assert not at.exception


def test_web_submission_and_refresh_do_not_repeat_task(app):
    at,factory=app
    at.sidebar.radio[0].set_value('创建回测').run()
    for item in at.number_input:
        if item.label=='短均线周期': item.set_value(2)
        if item.label=='长均线周期': item.set_value(3)
    at.button[0].click().run()
    assert not at.exception
    assert at.success
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(BacktestTask))==1
        assert session.scalar(select(func.count()).select_from(BacktestResult))==1
    at.run()
    with factory() as session:
        assert session.scalar(select(func.count()).select_from(BacktestTask))==1
    for page in ['任务与逐日回放','绩效与任务对比']:
        at.sidebar.radio[0].set_value(page).run()
        assert not at.exception


def test_tutorial_download_without_database(monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    at = AppTest.from_file(str(ROOT/'web_app.py'), default_timeout=45).run()
    at.sidebar.radio[0].set_value('使用教程')
    at.sidebar.selectbox[0].set_value('环境变量数据库').run()
    assert not at.exception
    assert any(title.value == '使用教程' for title in at.title)
    downloads = at.get('download_button')
    assert len(downloads) == 1
    assert downloads[0].label == '下载完整使用教程 PDF'
    assert (ROOT/'docs/量化研究工作台_使用教程.pdf').read_bytes().startswith(b'%PDF-')
