"""入口安全日志测试；MySQL错误由驱动异常模拟，不代表真实MySQL实测。"""
import importlib.util
import logging
from pathlib import Path

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

SPEC = importlib.util.spec_from_file_location(
    "import_cli_under_test", Path(__file__).parents[2] / "scripts/import_market_data.py"
)
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)

SECRET = "private_password_and_sql_values"


@pytest.mark.parametrize("error,expected", [
    (IntegrityError("secret SQL", {"password": SECRET}, Exception(1062, SECRET)),
     ["type=IntegrityError", "db_code=1062", "重复键冲突"]),
    (IntegrityError("secret SQL", {}, Exception(1452, SECRET)),
     ["type=IntegrityError", "db_code=1452", "完整性约束冲突"]),
    (IntegrityError("secret SQL", {}, Exception(SECRET)),
     ["type=IntegrityError", "db_code=unknown"]),
    (OperationalError("secret SQL", {}, Exception(1045, SECRET)),
     ["type=OperationalError", "db_code=1045"]),
    (SQLAlchemyError(SECRET), ["type=SQLAlchemyError", "db_code=unknown"]),
    (ValueError(SECRET), ["category=INPUT_ERROR"]),
    (FileNotFoundError(SECRET), ["category=INPUT_ERROR"]),
    (RuntimeError(SECRET), ["category=UNEXPECTED_ERROR"]),
])
def test_error_classification_does_not_leak_details(caplog, error, expected):
    with caplog.at_level(logging.ERROR):
        cli.log_import_error(error)
    for text in expected:
        assert text in caplog.text
    assert SECRET not in caplog.text
    assert "secret SQL" not in caplog.text
    assert "Traceback" not in caplog.text


def cli_args(monkeypatch):
    monkeypatch.setattr("sys.argv", ["import_market_data.py", "unused.csv", "--source", "synthetic/test",
        "--data-as-of", "2024-01-03", "--price-type", "test", "--synthetic", "--output", "unused"])


def test_initialization_error_has_safe_message_and_exit_one(monkeypatch, caplog):
    cli_args(monkeypatch)
    def fail():
        raise OperationalError("secret SQL", {}, Exception(1045, SECRET))
    monkeypatch.setattr(cli, "create_session_factory", fail)
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert "db_code=1045" in caplog.text
    assert SECRET not in caplog.text


def test_integrity_failure_disposes_engine_and_exits_one(monkeypatch, caplog):
    cli_args(monkeypatch)
    class Engine:
        disposed = False
        def dispose(self):
            self.disposed = True
    engine = Engine()
    class Factory:
        kw = {"bind": engine}
    monkeypatch.setattr(cli, "create_session_factory", lambda: Factory())
    def fail(*args):
        raise IntegrityError("secret SQL", {}, Exception(1062, SECRET))
    monkeypatch.setattr(cli, "import_csv", fail)
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert engine.disposed
    assert "db_code=1062" in caplog.text
    assert SECRET not in caplog.text
