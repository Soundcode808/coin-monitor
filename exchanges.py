"""
exchanges.py — 업비트·빗썸·바이낸스·비트겟 API 호출 모듈
가격 조회와 공통 코인 목록 추출을 담당.
"""
from __future__ import annotations

import logging

import requests

REQUEST_TIMEOUT_SEC = 10

UPBIT_TICKER_URL = "https://api.upbit.com/v1/ticker"
UPBIT_MARKETS_URL = "https://api.upbit.com/v1/market/all"
UPBIT_KRW_PREFIX = "KRW-"
UPBIT_CHUNK_SIZE = 100

BITHUMB_TICKER_URL = "https://api.bithumb.com/public/ticker/ALL_KRW"

BINANCE_TICKER_URL = "https://fapi.binance.com/fapi/v1/ticker/price"
BINANCE_TICKER_24H_URL = "https://fapi.binance.com/fapi/v1/ticker/24hr"
BINANCE_USDT_SUFFIX = "USDT"

# 24시간 거래량 최소값 (USDT) — 이 미만이면 사실상 거래 불가로 판단하고 제외
MIN_VOLUME_USDT = 50_000

BITGET_TICKER_URL = "https://api.bitget.com/api/v2/spot/market/tickers"
BITGET_USDT_SUFFIX = "USDT"

logger = logging.getLogger(__name__)


# ── 코인 목록 조회 ────────────────────────────────────────────

def fetch_upbit_krw_coins() -> list[str]:
    try:
        resp = requests.get(UPBIT_MARKETS_URL, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        return [
            item["market"].replace(UPBIT_KRW_PREFIX, "")
            for item in resp.json()
            if item["market"].startswith(UPBIT_KRW_PREFIX)
        ]
    except Exception as err:
        logger.error("업비트 마켓 목록 조회 실패: %s", err)
        return []


def fetch_bithumb_krw_coins() -> list[str]:
    try:
        resp = requests.get(BITHUMB_TICKER_URL, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        return [k for k in resp.json().get("data", {}).keys() if k != "date"]
    except Exception as err:
        logger.error("빗썸 마켓 목록 조회 실패: %s", err)
        return []


def fetch_binance_usdt_coins() -> list[str]:
    try:
        resp = requests.get(BINANCE_TICKER_URL, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        return [
            item["symbol"].replace(BINANCE_USDT_SUFFIX, "")
            for item in resp.json()
            if item["symbol"].endswith(BINANCE_USDT_SUFFIX)
        ]
    except Exception as err:
        logger.error("바이낸스 마켓 목록 조회 실패: %s", err)
        return []


def fetch_bitget_usdt_coins() -> list[str]:
    try:
        resp = requests.get(BITGET_TICKER_URL, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        return [
            item["symbol"].replace(BITGET_USDT_SUFFIX, "")
            for item in resp.json().get("data", [])
            if item["symbol"].endswith(BITGET_USDT_SUFFIX)
        ]
    except Exception as err:
        logger.error("비트겟 마켓 목록 조회 실패: %s", err)
        return []


# ── 공통 코인 추출 ────────────────────────────────────────────

def get_common_coins_multi(
    watch_coins: list[str],
    buy_exchanges: list[str],
    sell_exchanges: list[str],
) -> list[str]:
    """선택된 모든 거래소에 상장된 공통 코인 추출."""
    fetchers = {
        "upbit": fetch_upbit_krw_coins,
        "bithumb": fetch_bithumb_krw_coins,
        "binance": fetch_binance_usdt_coins,
        "bitget": fetch_bitget_usdt_coins,
    }
    selected = list(dict.fromkeys(buy_exchanges + sell_exchanges))
    coin_sets = []
    for ex in selected:
        coins = fetchers[ex]()
        if not coins:
            logger.warning("%s 코인 목록 조회 실패 — 해당 거래소 제외", ex)
            continue
        coin_sets.append(set(coins))

    if not coin_sets:
        return []

    common = sorted(coin_sets[0].intersection(*coin_sets[1:]))

    if watch_coins:
        watch_set = {c.upper() for c in watch_coins}
        filtered = [c for c in common if c in watch_set]
        logger.info("공통 코인 %d개 중 watch_coins 필터 후 %d개", len(common), len(filtered))
        return filtered

    logger.info("공통 코인 추출 완료: %d개 (%s)", len(common), " + ".join(selected))
    return common


# ── 가격 조회 ────────────────────────────────────────────────

def _fetch_upbit_chunk(chunk: list[str]) -> dict[str, float]:
    markets = ",".join(f"{UPBIT_KRW_PREFIX}{coin}" for coin in chunk)
    resp = requests.get(UPBIT_TICKER_URL, params={"markets": markets}, timeout=REQUEST_TIMEOUT_SEC)
    resp.raise_for_status()
    return {
        item["market"].replace(UPBIT_KRW_PREFIX, ""): float(item["trade_price"])
        for item in resp.json()
    }


def fetch_upbit_prices(coins: list[str]) -> dict[str, float]:
    if not coins:
        return {}
    result: dict[str, float] = {}
    for i in range(0, len(coins), UPBIT_CHUNK_SIZE):
        chunk = coins[i:i + UPBIT_CHUNK_SIZE]
        try:
            result.update(_fetch_upbit_chunk(chunk))
        except Exception as err:
            logger.error("업비트 가격 조회 실패 (청크 %d개): %s", len(chunk), err)
    return result


def fetch_bithumb_prices(coins: list[str]) -> dict[str, float]:
    if not coins:
        return {}
    try:
        resp = requests.get(BITHUMB_TICKER_URL, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json().get("data", {})
        return {
            coin: float(data[coin]["closing_price"])
            for coin in coins
            if coin in data and data[coin].get("closing_price")
        }
    except Exception as err:
        logger.error("빗썸 가격 조회 실패: %s", err)
        return {}


def fetch_binance_prices(coins: list[str]) -> dict[str, float]:
    """바이낸스 24hr 티커로 가격 조회 — 거래량 미달 코인 자동 제외."""
    if not coins:
        return {}
    target_symbols = {f"{coin}{BINANCE_USDT_SUFFIX}" for coin in coins}
    try:
        resp = requests.get(BINANCE_TICKER_24H_URL, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        result = {}
        for item in resp.json():
            if item["symbol"] not in target_symbols:
                continue
            price = float(item.get("lastPrice") or 0)
            volume = float(item.get("quoteVolume") or 0)
            if price <= 0 or volume < MIN_VOLUME_USDT:
                continue
            coin = item["symbol"].replace(BINANCE_USDT_SUFFIX, "")
            result[coin] = price
        return result
    except Exception as err:
        logger.error("바이낸스 가격 조회 실패: %s", err)
        return {}


def fetch_bitget_prices(coins: list[str]) -> dict[str, float]:
    """비트겟 티커로 가격 조회 — 거래량 미달 코인 자동 제외."""
    if not coins:
        return {}
    target_symbols = {f"{coin}{BITGET_USDT_SUFFIX}" for coin in coins}
    try:
        resp = requests.get(BITGET_TICKER_URL, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        result = {}
        for item in resp.json().get("data", []):
            if item["symbol"] not in target_symbols:
                continue
            price = float(item.get("lastPr") or 0)
            volume = float(item.get("quoteVolume") or 0)
            if price <= 0 or volume < MIN_VOLUME_USDT:
                continue
            coin = item["symbol"].replace(BITGET_USDT_SUFFIX, "")
            result[coin] = price
        return result
    except Exception as err:
        logger.error("비트겟 가격 조회 실패: %s", err)
        return {}


# ── 가격 집계 ────────────────────────────────────────────────

def get_korean_prices(
    coins: list[str],
    buy_exchanges: list[str],
) -> dict[str, tuple[float, str, float, str]]:
    """한국 거래소별 가격 집계 → dict[coin, (최저가, 거래소, 최고가, 거래소)]"""
    exchange_name = {"upbit": "업비트", "bithumb": "빗썸"}
    fetchers = {"upbit": fetch_upbit_prices, "bithumb": fetch_bithumb_prices}

    all_prices: dict[str, list[tuple[float, str]]] = {}
    for ex in buy_exchanges:
        for coin, price in fetchers[ex](coins).items():
            if price > 0:
                all_prices.setdefault(coin, []).append((price, exchange_name[ex]))

    result: dict[str, tuple[float, str, float, str]] = {}
    for coin, pairs in all_prices.items():
        lo = min(pairs, key=lambda x: x[0])
        hi = max(pairs, key=lambda x: x[0])
        result[coin] = (lo[0], lo[1], hi[0], hi[1])
    return result


def get_foreign_prices(
    coins: list[str],
    sell_exchanges: list[str],
    usd_krw: float,
) -> dict[str, tuple[float, str, float, str]]:
    """해외 거래소별 가격 집계 → dict[coin, (최저환산가, 거래소, 최고환산가, 거래소)]"""
    exchange_name = {"binance": "바이낸스", "bitget": "비트겟"}
    fetchers = {"binance": fetch_binance_prices, "bitget": fetch_bitget_prices}

    all_prices: dict[str, list[tuple[float, str]]] = {}
    for ex in sell_exchanges:
        for coin, usd_price in fetchers[ex](coins).items():
            if usd_price > 0:
                krw = usd_price * usd_krw
                all_prices.setdefault(coin, []).append((krw, exchange_name[ex]))

    result: dict[str, tuple[float, str, float, str]] = {}
    for coin, pairs in all_prices.items():
        lo = min(pairs, key=lambda x: x[0])
        hi = max(pairs, key=lambda x: x[0])
        result[coin] = (lo[0], lo[1], hi[0], hi[1])
    return result
