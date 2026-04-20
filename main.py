"""
main.py — 업비트-바이낸스 김치프리미엄 모니터링 메인 실행 파일
python main.py 로 실행, Ctrl+C 로 종료.
"""
from __future__ import annotations

import csv
import logging
import os
import sys
import time
from datetime import datetime

import yaml

from commander import start_commander_thread
from exchanges import get_common_coins_multi, get_foreign_prices, get_korean_prices
from fx import get_usd_krw

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
ALERTS_CSV_PATH = os.path.join(os.path.dirname(__file__), "alerts.csv")
CSV_HEADERS = ["시각", "코인", "매수거래소", "매수가", "매도거래소", "매도환산가", "괴리율"]

RETRY_ON_FAILURE_SEC = 10
COIN_REFRESH_INTERVAL = 20  # N 사이클마다 코인 목록 갱신

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

logging.basicConfig(level=logging.INFO, format=LOG_FORMAT, datefmt=LOG_DATE_FORMAT)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    if not os.path.exists(CONFIG_PATH):
        logger.error("config.yaml 파일이 없습니다. config.example.yaml을 복사해서 만들어 주세요.")
        sys.exit(1)
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def ensure_csv_header() -> None:
    if os.path.exists(ALERTS_CSV_PATH):
        return
    with open(ALERTS_CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerow(CSV_HEADERS)


def append_alert_to_csv(row: dict) -> None:
    with open(ALERTS_CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
        csv.DictWriter(f, fieldnames=CSV_HEADERS).writerow(row)


def calc_divergence(buy_krw: float, sell_krw: float) -> float:
    """괴리율(%) = (매수가 - 매도환산가) / 매도환산가 × 100. 음수 = 역프리미엄."""
    if sell_krw == 0:
        return 0.0
    return (buy_krw - sell_krw) / sell_krw * 100


# 거래소명을 바이낸스(4글자) 기준으로 정렬하기 위한 전각 공백 패딩
EX_PAD = {"빗썸": "　　", "업비트": "　", "바이낸스": "", "비트겟": "　"}


def _ex(name: str) -> str:
    return name + EX_PAD.get(name, "")


def _fmt(price: float) -> str:
    """가격을 크기에 맞게 소수점 자릿수 조정해서 반환."""
    if price >= 100:
        return f"{price:,.0f}원"
    elif price >= 10:
        return f"{price:,.1f}원"
    elif price >= 1:
        return f"{price:,.2f}원"
    else:
        return f"{price:,.4f}원"


def build_alert_message(
    coin: str,
    korean_krw: float,
    korean_ex: str,
    foreign_krw: float,
    foreign_ex: str,
    divergence: float,
) -> str:
    abs_div = abs(divergence)
    sign = f"+{abs_div:.2f}" if divergence > 0 else f"-{abs_div:.2f}"

    if divergence < 0:
        label = "역프"
        buy_ex, buy_krw = korean_ex, korean_krw
        sell_ex, sell_krw = foreign_ex, foreign_krw
    else:
        label = "김프"
        buy_ex, buy_krw = foreign_ex, foreign_krw
        sell_ex, sell_krw = korean_ex, korean_krw

    sep = "─" * 18
    return (
        f"{sep}\n"
        f"<b>{coin}  {sign}%  [{label}]</b>\n"
        f"{sep}\n"
        f"🟩 사기   {_ex(buy_ex)}   {_fmt(buy_krw)}\n"
        f"           ⬇️\n"
        f"🟥 팔기   {_ex(sell_ex)}   {_fmt(sell_krw)}"
    )


def is_in_cooldown(coin: str, last_alerted: dict, cooldown_sec: int) -> bool:
    last = last_alerted.get(coin)
    return last is not None and (time.time() - last) < cooldown_sec


class CycleContext:
    def __init__(self, config: dict, notifier, last_alerted: dict):
        self.threshold_min = float(config.get("threshold_min", 1.0))
        threshold_max = config.get("threshold_max")
        self.threshold_max = float(threshold_max) if threshold_max is not None else None
        self.cooldown_sec = int(config.get("cooldown_sec", 600))
        self.notifier = notifier
        self.last_alerted = last_alerted


def process_one_coin(
    coin: str,
    korean_krw: float,
    korean_ex: str,
    foreign_krw: float,
    foreign_ex: str,
    ctx: CycleContext,
) -> None:
    divergence = calc_divergence(korean_krw, foreign_krw)
    abs_div = abs(divergence)

    if abs_div < ctx.threshold_min:
        return
    if ctx.threshold_max is not None and abs_div > ctx.threshold_max:
        return
    if is_in_cooldown(coin, ctx.last_alerted, ctx.cooldown_sec):
        return

    message = build_alert_message(coin, korean_krw, korean_ex, foreign_krw, foreign_ex, divergence)
    ctx.notifier.send(message)
    ctx.last_alerted[coin] = time.time()

    label = "역프" if divergence < 0 else "김프"
    sign = "-" if divergence < 0 else "+"
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    append_alert_to_csv({
        "시각": now_str,
        "코인": coin,
        "매수거래소": korean_ex if divergence < 0 else foreign_ex,
        "매수가": f"{korean_krw:.0f}" if divergence < 0 else f"{foreign_krw:.0f}",
        "매도거래소": foreign_ex if divergence < 0 else korean_ex,
        "매도환산가": f"{foreign_krw:.0f}" if divergence < 0 else f"{korean_krw:.0f}",
        "괴리율": f"{sign}{abs_div:.2f}%",
    })
    logger.info("알림 발송: %s %s%.2f%% [%s]", coin, sign, abs_div, label)


def run_cycle(
    coins: list[str],
    config: dict,
    notifier,
    last_alerted: dict,
    is_first: bool,
) -> None:
    buy_exchanges = config.get("buy_exchanges", ["bithumb"])
    sell_exchanges = config.get("sell_exchanges", ["binance"])

    usd_krw = get_usd_krw(config)
    korean_data = get_korean_prices(coins, buy_exchanges)
    foreign_data = get_foreign_prices(coins, sell_exchanges, usd_krw)

    if not korean_data:
        logger.warning("한국 거래소 가격 조회 결과 없음. 다음 사이클에서 재시도합니다.")
        return
    if not foreign_data:
        logger.warning("해외 거래소 가격 조회 결과 없음. 다음 사이클에서 재시도합니다.")
        return

    if is_first:
        return

    ctx = CycleContext(config, notifier, last_alerted)
    alerted_count = 0
    skipped_count = 0
    for coin in coins:
        if coin not in korean_data or coin not in foreign_data:
            continue
        kr_lo, kr_lo_ex, kr_hi, kr_hi_ex = korean_data[coin]
        fo_lo, fo_lo_ex, fo_hi, fo_hi_ex = foreign_data[coin]

        # 김프: 가장 비싼 한국가 vs 가장 싼 해외가
        div_kimchi = calc_divergence(kr_hi, fo_lo)
        # 역프: 가장 싼 한국가 vs 가장 비싼 해외가
        div_yeok = calc_divergence(kr_lo, fo_hi)

        if abs(div_kimchi) >= abs(div_yeok):
            korean_krw, korean_ex = kr_hi, kr_hi_ex
            foreign_krw, foreign_ex = fo_lo, fo_lo_ex
        else:
            korean_krw, korean_ex = kr_lo, kr_lo_ex
            foreign_krw, foreign_ex = fo_hi, fo_hi_ex

        prev_alerted = len(ctx.last_alerted)
        try:
            process_one_coin(coin, korean_krw, korean_ex, foreign_krw, foreign_ex, ctx)
        except Exception as err:
            logger.error("코인 처리 중 오류 (%s): %s", coin, err)
        if len(ctx.last_alerted) > prev_alerted:
            alerted_count += 1
        else:
            skipped_count += 1

    if alerted_count == 0:
        checked = sum(1 for c in coins if c in korean_data and c in foreign_data)
        logger.info("알림 없음 — %d개 코인 조회, 기준 범위 내 없음 또는 쿨다운 중", checked)


def build_notifier(config: dict):
    from notifier import CompositeNotifier, SoundNotifier, TelegramNotifier

    notifiers = []
    tg = config.get("telegram", {})
    token = tg.get("bot_token", "")
    chat_id = str(tg.get("chat_id", ""))
    placeholders = {"여기에_봇토큰_입력", "여기에_챗ID_입력", ""}
    if token not in placeholders and chat_id not in placeholders:
        notifiers.append(TelegramNotifier(token, chat_id))
    else:
        logger.warning("텔레그램 설정 없음 — 텔레그램 알림 비활성화")
    if config.get("sound", {}).get("enabled", True):
        notifiers.append(SoundNotifier())
    return CompositeNotifier(notifiers)


def refresh_coins(config: dict) -> list[str]:
    buy_exchanges = config.get("buy_exchanges", ["bithumb"])
    sell_exchanges = config.get("sell_exchanges", ["binance"])
    watch_coins = config.get("watch_coins") or []
    coins = get_common_coins_multi(watch_coins, buy_exchanges, sell_exchanges)
    if not coins:
        logger.error("모니터링할 공통 코인이 없습니다.")
    return coins


def main() -> None:
    logger.info("=== 코인 모니터링 시작 ===")
    config = load_config()
    ensure_csv_header()

    notifier = build_notifier(config)

    tg = config.get("telegram", {})
    start_commander_thread(
        bot_token=tg.get("bot_token", ""),
        chat_id=str(tg.get("chat_id", "")),
        config_path=CONFIG_PATH,
    )

    logger.info("공통 코인 추출 중...")
    coins = refresh_coins(config)
    if not coins:
        sys.exit(1)

    check_interval = int(config.get("check_interval_sec", 30))
    skip_first = config.get("skip_first_cycle", True)
    last_alerted: dict[str, float] = {}
    cycle_count = 0
    is_first_cycle = True

    logger.info(
        "모니터링 시작 (간격: %d초, 기준: %.1f%%~%s)",
        check_interval,
        config.get("threshold_min", 1.0),
        str(config.get("threshold_max")) + "%" if config.get("threshold_max") else "제한없음",
    )
    if skip_first:
        logger.info("첫 사이클은 베이스라인 수집만 하고 알림을 발송하지 않습니다.")

    while True:
        try:
            config = load_config()
            check_interval = int(config.get("check_interval_sec", 30))

            if cycle_count % COIN_REFRESH_INTERVAL == 0 and cycle_count > 0:
                logger.info("코인 목록 갱신 중...")
                refreshed = refresh_coins(config)
                if refreshed:
                    coins = refreshed

            run_cycle(
                coins, config, notifier, last_alerted,
                is_first=(skip_first and is_first_cycle),
            )
            is_first_cycle = False
            cycle_count += 1
            time.sleep(check_interval)

        except KeyboardInterrupt:
            logger.info("사용자 종료 요청 (Ctrl+C). 모니터링을 종료합니다.")
            break
        except Exception as err:
            logger.error("사이클 전체 실패: %s — %d초 후 재시도", err, RETRY_ON_FAILURE_SEC)
            time.sleep(RETRY_ON_FAILURE_SEC)


if __name__ == "__main__":
    main()
