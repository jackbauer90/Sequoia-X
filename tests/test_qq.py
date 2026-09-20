"""QQ OneBot 通知测试。"""

import logging
from unittest.mock import MagicMock, patch

from sequoia_x.core.config import Settings
from sequoia_x.notify.qq import QQNotifier


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "db_path": "data/test.db",
        "start_date": "2024-01-01",
        "qq_bot_api_url": "http://127.0.0.1:3000",
        "qq_target_type": "group",
        "qq_target_id": 123456789,
    }
    values.update(overrides)
    return Settings(**values)


def test_group_notification_uses_onebot_group_action_and_contains_all_symbols() -> None:
    """若群聊动作、目标字段或任一股票被漏掉，此测试应失败。"""
    notifier = QQNotifier(make_settings())

    with (
        patch.object(
            QQNotifier,
            "_get_stock_names",
            return_value={"000001": "平安银行", "600519": "贵州茅台"},
        ),
        patch("requests.post") as mock_post,
    ):
        mock_post.return_value = MagicMock(
            status_code=200,
            text='{"status":"ok","retcode":0}',
            json=lambda: {"status": "ok", "retcode": 0},
        )
        notifier.send(["000001", "600519"], "TestStrategy")

    assert mock_post.call_args.args[0] == "http://127.0.0.1:3000/send_group_msg"
    payload = mock_post.call_args.kwargs["json"]
    assert payload["group_id"] == 123456789
    assert payload["auto_escape"] is True
    assert "平安银行（000001）" in payload["message"]
    assert "贵州茅台（600519）" in payload["message"]


def test_private_notification_uses_user_id_and_bearer_token() -> None:
    """若私聊误投群聊或鉴权令牌未发送，此测试应失败。"""
    notifier = QQNotifier(
        make_settings(
            qq_target_type="private",
            qq_target_id=987654321,
            qq_bot_access_token="secret-token",
        )
    )

    with (
        patch.object(QQNotifier, "_get_stock_names", return_value={"000001": "平安银行"}),
        patch("requests.post") as mock_post,
    ):
        mock_post.return_value = MagicMock(
            status_code=200,
            text='{"status":"ok","retcode":0}',
            json=lambda: {"status": "ok", "retcode": 0},
        )
        notifier.send(["000001"], "TestStrategy")

    assert mock_post.call_args.args[0] == "http://127.0.0.1:3000/send_private_msg"
    assert mock_post.call_args.kwargs["json"]["user_id"] == 987654321
    assert mock_post.call_args.kwargs["headers"] == {
        "Authorization": "Bearer secret-token"
    }


def test_onebot_failure_logs_error() -> None:
    """若 OneBot 业务失败被误报为成功，此测试应失败。"""
    import sequoia_x.notify.qq as qq_module

    notifier = QQNotifier(make_settings())
    qq_logger = logging.getLogger(qq_module.__name__)
    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _ListHandler(logging.ERROR)
    qq_logger.addHandler(handler)
    try:
        with (
            patch.object(QQNotifier, "_get_stock_names", return_value={"000001": "平安银行"}),
            patch("requests.post") as mock_post,
        ):
            mock_post.return_value = MagicMock(
                status_code=200,
                text='{"status":"failed","retcode":100}',
                json=lambda: {"status": "failed", "retcode": 100},
            )
            notifier.send(["000001"], "TestStrategy")
    finally:
        qq_logger.removeHandler(handler)

    assert any(record.levelno == logging.ERROR for record in records)
