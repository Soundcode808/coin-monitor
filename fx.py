"""
fx.py — USD/KRW 환율 조회 모듈
폴백 체인: 한국수출입은행 → 한국은행 ECOS → open.er-api.com
성공한 소스에서 바로 반환하고 다음 폴백은 호출하지 않음.
1시간 캐시로 API 과호출 방지.
"""

from __future__ import annotations

import time
import logging

import requests

# 요청 타임아웃 (초)
REQUEST_TIMEOUT_SEC = 10

# 기본 캐시 유지 시간 (분 → 초 변환용)
MINUTES_TO_SECONDS = 60

logger = logging.getLogger(__name__)


class FxCache:
    """환율 캐시 — 마지막으로 성공한 환율과 조회 시각을 보관"""

    def __init__(self):
        self._rate: float | None = None
        self._fetched_at: float = 0.0

    def is_valid(self, cache_minutes: int) -> bool:
        """캐시가 아직 유효한지 확인"""
        if self._rate is None:
            return False
        age_sec = time.time() - self._fetched_at
        return age_sec < cache_minutes * MINUTES_TO_SECONDS

    def get(self) -> float | None:
        """캐시된 환율 반환"""
        return self._rate

    def set(self, rate: float) -> None:
        """환율 캐시 저장 — 0 이하 값은 저장 거부"""
        if rate <= 0:
            raise ValueError(f"유효하지 않은 환율 값: {rate}")
        self._rate = rate
        self._fetched_at = time.time()


# 모듈 전역 캐시 인스턴스
_cache = FxCache()


def _fetch_exim(api_key: str) -> float | None:
    """한국수출입은행 API로 USD/KRW 환율 조회"""
    if not api_key:
        return None
    url = "https://www.koreaexim.go.kr/site/program/financial/exchangeJSON"
    params = {
        "authkey": api_key,
        "searchdate": "",
        "data": "AP01",
    }
    try:
        resp = requests.get(url, params=params, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        # 주말/공휴일에는 빈 배열 반환 — None으로 처리해 폴백 유도
        for item in data:
            if item.get("cur_unit") == "USD":
                rate_str = item.get("deal_bas_r", "").replace(",", "")
                rate = float(rate_str)
                if rate <= 0:
                    raise ValueError(f"수출입은행 환율 비정상값: {rate}")
                return rate
    except Exception as err:
        logger.warning("수출입은행 환율 조회 실패: %s", err)
    return None


def _fetch_ecos(api_key: str) -> float | None:
    """한국은행 ECOS API로 USD/KRW 환율 조회"""
    if not api_key:
        return None
    import datetime
    today = datetime.date.today().strftime("%Y%m%d")
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{api_key}/json/kr"
        f"/1/1/731Y001/DD/{today}/{today}/0000001"
    )
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("StatisticSearch", {}).get("row", [])
        if rows:
            rate = float(rows[0]["DATA_VALUE"])
            if rate <= 0:
                raise ValueError(f"한국은행 ECOS 환율 비정상값: {rate}")
            return rate
    except Exception as err:
        logger.warning("한국은행 ECOS 환율 조회 실패: %s", err)
    return None


def _fetch_open_er() -> float | None:
    """open.er-api.com 무료 API로 USD/KRW 환율 조회"""
    url = "https://open.er-api.com/v6/latest/USD"
    try:
        resp = requests.get(url, timeout=REQUEST_TIMEOUT_SEC)
        resp.raise_for_status()
        data = resp.json()
        rate = float(data["rates"]["KRW"])
        if rate <= 0:
            raise ValueError(f"open.er-api 환율 비정상값: {rate}")
        return rate
    except Exception as err:
        logger.warning("open.er-api 환율 조회 실패: %s", err)
    return None


def get_usd_krw(config: dict) -> float:
    """
    USD/KRW 환율 반환 — 캐시 유효하면 캐시 사용, 만료 시 폴백 체인 순서대로 조회.
    모든 소스 실패 시 RuntimeError 발생.
    """
    fx_config = config.get("fx", {})
    cache_minutes = int(fx_config.get("cache_minutes", 60))

    if _cache.is_valid(cache_minutes):
        return _cache.get()

    exim_key = fx_config.get("exim_api_key", "")
    ecos_key = fx_config.get("ecos_api_key", "")

    fetchers = [
        ("한국수출입은행", lambda: _fetch_exim(exim_key)),
        ("한국은행 ECOS", lambda: _fetch_ecos(ecos_key)),
        ("open.er-api.com", _fetch_open_er),
    ]

    for source_name, fetcher in fetchers:
        rate = fetcher()
        if rate is not None:
            logger.info("환율 조회 성공 (%s): %.2f", source_name, rate)
            _cache.set(rate)
            return rate

    raise RuntimeError("모든 환율 소스 조회 실패. 인터넷 연결 및 API 키를 확인하세요.")
