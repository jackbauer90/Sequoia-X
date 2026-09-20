"""QQ 通知模块：通过 OneBot 11 HTTP API 推送选股结果。"""

from datetime import date

import requests

from sequoia_x.core.config import Settings
from sequoia_x.core.logger import get_logger

logger = get_logger(__name__)


class QQNotifier:
    """通过 OneBot 11 将选股结果发送到 QQ 群或 QQ 私聊。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _to_xueqiu_code(code: str) -> str:
        """将纯数字代码转为雪球格式：6开头→SH，4/8开头→BJ，其余→SZ。"""
        if code.startswith("6"):
            return f"SH{code}"
        if code.startswith(("4", "8")):
            return f"BJ{code}"
        return f"SZ{code}"

    @staticmethod
    def _get_stock_names(symbols: list[str]) -> dict[str, str]:
        """通过 baostock 批量查询股票名称，返回 {code: name} 映射。"""
        import baostock as bs

        bs.login()
        mapping = {}
        for code in symbols:
            prefix = "sh" if code.startswith(("6", "9")) else "sz"
            rs = bs.query_stock_basic(code=f"{prefix}.{code}")
            while rs.next():
                row = rs.get_row_data()
                mapping[code] = row[1]
        bs.logout()
        return mapping

    def _build_message(self, symbols: list[str], strategy_name: str) -> str:
        names = self._get_stock_names(symbols)
        stocks = []
        for code in symbols:
            xueqiu_code = self._to_xueqiu_code(code)
            name = names.get(code, xueqiu_code)
            stocks.append(f"- {name}（{code}） https://xueqiu.com/S/{xueqiu_code}")

        stock_text = "\n".join(stocks) if stocks else "（无选股结果）"
        return (
            f"📈 Sequoia-X 选股播报 | {strategy_name}\n"
            f"日期：{date.today():%Y-%m-%d}\n"
            f"策略：{strategy_name}\n"
            f"选股数量：{len(symbols)}\n\n"
            f"选股列表：\n{stock_text}"
        )

    def send(self, symbols: list[str], strategy_name: str) -> None:
        """将选股结果发送到配置的 QQ 群或 QQ 私聊。"""
        target_type = self.settings.qq_target_type
        action = "send_group_msg" if target_type == "group" else "send_private_msg"
        target_field = "group_id" if target_type == "group" else "user_id"
        url = f"{self.settings.qq_bot_api_url.rstrip('/')}/{action}"
        payload = {
            target_field: self.settings.qq_target_id,
            "message": self._build_message(symbols, strategy_name),
            "auto_escape": True,
        }
        headers = {}
        if self.settings.qq_bot_access_token:
            headers["Authorization"] = f"Bearer {self.settings.qq_bot_access_token}"

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=10)
            result = response.json()
            if (
                response.status_code != 200
                or result.get("status") != "ok"
                or result.get("retcode") != 0
            ):
                logger.error(
                    f"QQ 推送失败 HTTP状态={response.status_code} OneBot响应={response.text}"
                )
            else:
                logger.info(f"QQ 推送成功，共 {len(symbols)} 只股票")
        except (requests.RequestException, ValueError) as exc:
            logger.error(f"QQ 推送请求异常：{exc}")
