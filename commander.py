"""
commander.py — 텔레그램 명령어 처리 모듈
!명령어 를 수신해서 config.yaml을 실시간으로 수정한다.
"""
from __future__ import annotations

import logging
import threading
import time

import requests
import yaml

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SEC = 10
POLL_INTERVAL_SEC = 2

# 한국 거래소 (매수측)
KOREAN_EXCHANGES = {"빗썸": "bithumb", "업비트": "upbit"}
# 해외 거래소 (매도측)
FOREIGN_EXCHANGES = {"바이낸스": "binance", "비트겟": "bitget"}
ALL_EXCHANGES = {**KOREAN_EXCHANGES, **FOREIGN_EXCHANGES}

# 거래소명 → 한글 변환 (로그/메시지용)
EXCHANGE_KR = {"bithumb": "빗썸", "upbit": "업비트", "binance": "바이낸스", "bitget": "비트겟"}

DEFAULT_BUY = ["bithumb"]
DEFAULT_SELL = ["binance"]

TRADING_FEES = {
    "bithumb": 0.0025,
    "upbit":   0.0005,
    "binance": 0.001,
    "bitget":  0.001,
}


def _fmt_price(price: float) -> str:
    if price >= 100:
        return f"{price:,.0f}원"
    elif price >= 10:
        return f"{price:,.1f}원"
    elif price >= 1:
        return f"{price:,.2f}원"
    else:
        return f"{price:,.4f}원"

HELP_TEXT = """📖 <b>명령어 도움말</b>
━━━━━━━━━━━━━━
<b>!거래소 [거래소명...]</b>
  모니터링할 거래소 설정
  한국 거래소(빗썸·업비트)와 해외 거래소(바이낸스·비트겟)를
  자유롭게 조합하면 역프리미엄을 자동으로 비교합니다
  예) !거래소 빗썸 바이낸스
  예) !거래소 빗썸 업비트 바이낸스 비트겟

<b>!거래소 삭제</b>
  거래소 설정을 기본값으로 초기화
  (빗썸 + 바이낸스)

<b>!기준 [최소%] [최대%]</b>
  알림 괴리율 기준 설정
  예) !기준 1.5        → 1.5% 이상 전부 알림
  예) !기준 1.5 10.0  → 1.5% ~ 10.0% 사이만 알림
  ※ 최댓값을 두면 가격이 이상한 코인이 자동 제외됩니다

<b>!시간 [분]</b>
  가격 조회 시간 설정 (분 단위, 소수 가능)
  예) !시간 0.5   → 30초마다 조회
  예) !시간 1     → 1분마다 조회
  예) !시간 3.5   → 3분 30초마다 조회

<b>!코인 [심볼...]</b>
  특정 코인만 모니터링
  예) !코인 BTC ETH SOL
  예) !코인 전체       → 전체 코인 모니터링

<b>![코인] [투자금]</b>
  수익 계산 (현재 설정된 거래소 기준)
  예) !IQ 1000000
  예) !BTC 500000

<b>!상태</b>
  현재 설정 전체 확인

<b>!도움 / !도움말</b>
  이 도움말 표시
━━━━━━━━━━━━━━
⚠️ 선택한 모든 거래소에 실제로 상장·거래되는 코인만 알림이 발송됩니다."""


class Commander:
    """텔레그램 명령어 수신 및 config.yaml 실시간 수정 담당"""

    def __init__(self, bot_token: str, chat_id: str, config_path: str):
        self._bot_token = bot_token
        self._chat_id = chat_id
        self._config_path = config_path
        self._offset: int = 0
        self._lock = threading.Lock()

    def _send(self, text: str) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/sendMessage"
        try:
            requests.post(url, json={
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": "HTML",
            }, timeout=REQUEST_TIMEOUT_SEC)
        except Exception as err:
            logger.error("명령어 응답 전송 실패: %s", err)

    def _load_config(self) -> dict:
        with open(self._config_path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _save_config(self, config: dict) -> None:
        with open(self._config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def _handle_exchange(self, args: list[str], config: dict) -> str:
        if not args:
            return "❌ 거래소를 입력해주세요.\n예) !거래소 빗썸 바이낸스"

        if len(args) == 1 and args[0] == "삭제":
            config["buy_exchanges"] = DEFAULT_BUY
            config["sell_exchanges"] = DEFAULT_SELL
            return "✅ 거래소 설정 초기화 완료\n🇰🇷 한국: 빗썸  |  🌐 해외: 바이낸스"

        buy_exchanges, sell_exchanges, unknown = [], [], []
        for arg in args:
            if arg in KOREAN_EXCHANGES:
                buy_exchanges.append(KOREAN_EXCHANGES[arg])
            elif arg in FOREIGN_EXCHANGES:
                sell_exchanges.append(FOREIGN_EXCHANGES[arg])
            else:
                unknown.append(arg)

        if unknown:
            return f"❌ 지원하지 않는 거래소: {', '.join(unknown)}\n지원: 빗썸, 업비트, 바이낸스, 비트겟"
        if not buy_exchanges:
            return "❌ 한국 거래소(빗썸 또는 업비트)를 최소 1개 포함해주세요."
        if not sell_exchanges:
            return "❌ 해외 거래소(바이낸스 또는 비트겟)를 최소 1개 포함해주세요."

        config["buy_exchanges"] = buy_exchanges
        config["sell_exchanges"] = sell_exchanges

        buy_names = ", ".join(EXCHANGE_KR[e] for e in buy_exchanges)
        sell_names = ", ".join(EXCHANGE_KR[e] for e in sell_exchanges)
        return (
            f"✅ 거래소 설정 완료\n"
            f"🇰🇷 한국: {buy_names}\n"
            f"🌐 해외: {sell_names}\n\n"
            f"코인 목록은 다음 갱신 시 자동 업데이트됩니다."
        )

    def _handle_threshold(self, args: list[str], config: dict) -> str:
        try:
            if len(args) == 1:
                mn = float(args[0])
                if mn <= 0:
                    return "❌ 0보다 큰 숫자를 입력해주세요."
                config["threshold_min"] = mn
                config["threshold_max"] = None
                return f"✅ 알림 기준 설정 완료\n📌 {mn}% 이상이면 알림"
            elif len(args) == 2:
                mn, mx = float(args[0]), float(args[1])
                if mn <= 0 or mx <= 0:
                    return "❌ 0보다 큰 숫자를 입력해주세요."
                if mn >= mx:
                    return "❌ 최솟값이 최댓값보다 작아야 합니다."
                config["threshold_min"] = mn
                config["threshold_max"] = mx
                return f"✅ 알림 기준 설정 완료\n📌 {mn}% ~ {mx}% 사이만 알림"
            else:
                return "❌ 예) !기준 1.5  또는  !기준 1.5 10.0"
        except ValueError:
            return "❌ 숫자를 입력해주세요.\n예) !기준 1.5  또는  !기준 1.5 10.0"

    def _handle_interval(self, args: list[str], config: dict) -> str:
        if len(args) != 1:
            return "❌ 예) !시간 1  또는  !시간 0.5  또는  !시간 3.5"
        try:
            minutes = float(args[0])
            if minutes <= 0:
                return "❌ 0보다 큰 숫자를 입력해주세요."
            seconds = round(minutes * 60)
            if seconds < 10:
                return "❌ 최소 10초(0.17분) 이상으로 설정해주세요."
            config["check_interval_sec"] = seconds
            m, s = divmod(seconds, 60)
            time_str = f"{m}분 {s}초" if m and s else (f"{m}분" if m else f"{s}초")
            return f"✅ 조회 시간 설정 완료\n📌 {minutes}분 ({time_str})마다 조회"
        except ValueError:
            return "❌ 숫자를 입력해주세요.\n예) !시간 1  또는  !시간 0.5"

    def _handle_coins(self, args: list[str], config: dict) -> str:
        if not args or (len(args) == 1 and args[0] == "전체"):
            config["watch_coins"] = []
            return "✅ 전체 코인 모니터링으로 설정 완료"
        coins = [c.upper() for c in args]
        config["watch_coins"] = coins
        return f"✅ 모니터링 코인 설정 완료\n📌 {', '.join(coins)}"

    def _handle_status(self, config: dict) -> str:
        buy_exs = config.get("buy_exchanges", DEFAULT_BUY)
        sell_exs = config.get("sell_exchanges", DEFAULT_SELL)
        buy_names = ", ".join(EXCHANGE_KR.get(e, e) for e in buy_exs)
        sell_names = ", ".join(EXCHANGE_KR.get(e, e) for e in sell_exs)
        mn = config.get("threshold_min", 1.0)
        mx = config.get("threshold_max")
        threshold_str = f"{mn}% ~ {mx}%" if mx else f"{mn}% 이상"
        coins = config.get("watch_coins") or []
        coins_str = ", ".join(coins) if coins else "전체"
        interval = config.get("check_interval_sec", 30)
        return (
            f"⚙️ <b>현재 설정</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"🇰🇷 한국 거래소: {buy_names}\n"
            f"🌐 해외 거래소: {sell_names}\n"
            f"알림 기준: {threshold_str}\n"
            f"모니터링 코인: {coins_str}\n"
            f"조회 시간: {interval}초"
        )

    def _handle_profit_calc(self, coin: str, args: list[str], config: dict) -> str:
        if not args:
            return f"❌ 예) !{coin} 1000000"
        try:
            investment = float(args[0].replace(",", ""))
            if investment <= 0:
                return "❌ 투자금액은 0보다 커야 합니다."
        except ValueError:
            return f"❌ 금액을 숫자로 입력해주세요. 예) !{coin} 1000000"

        buy_exchanges = config.get("buy_exchanges", DEFAULT_BUY)
        sell_exchanges = config.get("sell_exchanges", DEFAULT_SELL)

        try:
            from fx import get_usd_krw
            usd_krw = get_usd_krw(config)
        except Exception as err:
            return f"❌ 환율 조회 실패: {err}"

        try:
            from exchanges import get_foreign_prices, get_korean_prices
            korean_data = get_korean_prices([coin], buy_exchanges)
            foreign_data = get_foreign_prices([coin], sell_exchanges, usd_krw)
        except Exception as err:
            return f"❌ 가격 조회 실패: {err}"

        if coin not in korean_data:
            return f"❌ {coin}: 설정된 한국 거래소에서 가격을 찾을 수 없습니다."
        if coin not in foreign_data:
            return f"❌ {coin}: 설정된 해외 거래소에서 가격을 찾을 수 없습니다."

        kr_lo, kr_lo_ex, kr_hi, kr_hi_ex = korean_data[coin]
        fo_lo, fo_lo_ex, fo_hi, fo_hi_ex = foreign_data[coin]

        div_kimchi = (kr_hi - fo_lo) / fo_lo * 100
        div_yeok = (kr_lo - fo_hi) / fo_hi * 100

        if abs(div_kimchi) >= abs(div_yeok):
            buy_price, buy_ex_name = fo_lo, fo_lo_ex
            sell_price, sell_ex_name = kr_hi, kr_hi_ex
            divergence = div_kimchi
            label = "김프"
        else:
            buy_price, buy_ex_name = kr_lo, kr_lo_ex
            sell_price, sell_ex_name = fo_hi, fo_hi_ex
            divergence = div_yeok
            label = "역프"

        buy_ex_key = ALL_EXCHANGES.get(buy_ex_name, "binance")
        sell_ex_key = ALL_EXCHANGES.get(sell_ex_name, "bithumb")
        buy_fee_rate = TRADING_FEES.get(buy_ex_key, 0.001)
        sell_fee_rate = TRADING_FEES.get(sell_ex_key, 0.001)

        buy_fee = investment * buy_fee_rate
        qty = (investment - buy_fee) / buy_price
        gross = qty * sell_price
        sell_fee = gross * sell_fee_rate
        final = gross - sell_fee
        total_fee = buy_fee + sell_fee
        profit = final - investment
        profit_pct = profit / investment * 100
        sign = "+" if profit >= 0 else ""

        breakeven_price = investment / (qty * (1 - sell_fee_rate))

        return (
            f"💰 <b>{coin} {label} {sign}{divergence:.2f}%</b>\n"
            f"━━━━━━━━━━━━━━\n"
            f"투자금:        {investment:>12,.0f}원\n"
            f"구매 수수료:   {buy_fee:>12,.0f}원  ({buy_fee_rate*100:.2f}%, {buy_ex_name})\n"
            f"매도 수수료:   {sell_fee:>12,.0f}원  ({sell_fee_rate*100:.2f}%, {sell_ex_name})\n"
            f"총 수수료:     {total_fee:>12,.0f}원\n"
            f"━━━━━━━━━━━━━━\n"
            f"수익:          {sign}{profit:>11,.0f}원\n"
            f"최종 수령:     {final:>12,.0f}원  ({sign}{profit_pct:.2f}%)\n"
            f"손익분기가:    {_fmt_price(breakeven_price)}"
        )

    def _process_command(self, text: str) -> None:
        text = text.strip()
        if not text.startswith("!"):
            return
        parts = text[1:].split()
        if not parts:
            return
        cmd, args = parts[0], parts[1:]

        with self._lock:
            if cmd in ("도움", "도움말"):
                self._send(HELP_TEXT)
                return
            config = self._load_config()
            if cmd == "상태":
                self._send(self._handle_status(config))
                return
            elif cmd == "거래소":
                reply = self._handle_exchange(args, config)
            elif cmd == "기준":
                reply = self._handle_threshold(args, config)
            elif cmd == "시간":
                reply = self._handle_interval(args, config)
            elif cmd == "코인":
                reply = self._handle_coins(args, config)
            elif cmd.isascii() and cmd.replace("1", "").isalpha():
                self._send(self._handle_profit_calc(cmd.upper(), args, config))
                return
            else:
                self._send(f"❓ 알 수 없는 명령어: !{cmd}\n!도움 을 입력하면 명령어 목록을 볼 수 있어요.")
                return
            self._save_config(config)
            self._send(reply)

    def _poll(self) -> None:
        url = f"https://api.telegram.org/bot{self._bot_token}/getUpdates"
        try:
            resp = requests.get(
                url,
                params={"offset": self._offset, "timeout": 1},
                timeout=REQUEST_TIMEOUT_SEC,
            )
            resp.raise_for_status()
            for update in resp.json().get("result", []):
                self._offset = update["update_id"] + 1
                text = update.get("message", {}).get("text", "")
                if text:
                    self._process_command(text)
        except Exception as err:
            logger.debug("명령어 폴링 중 오류: %s", err)

    def run(self) -> None:
        logger.info("텔레그램 명령어 수신 대기 중 (!도움 으로 명령어 확인)")
        while True:
            self._poll()
            time.sleep(POLL_INTERVAL_SEC)


def start_commander_thread(bot_token: str, chat_id: str, config_path: str) -> None:
    commander = Commander(bot_token, chat_id, config_path)
    thread = threading.Thread(target=commander.run, daemon=True, name="CommanderThread")
    thread.start()
