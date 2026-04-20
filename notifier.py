"""
notifier.py — 알림 발송 모듈
텔레그램, Windows 사운드, 복합 알림을 담당.
추후 KakaoNotifier 추가 시 Notifier를 상속하면 됨.
"""

import logging
from abc import ABC, abstractmethod

import requests

# 요청 타임아웃 (초)
REQUEST_TIMEOUT_SEC = 10

# 텔레그램 API 엔드포인트 템플릿
TELEGRAM_SEND_MESSAGE_URL = "https://api.telegram.org/bot{token}/sendMessage"

logger = logging.getLogger(__name__)


class Notifier(ABC):
    """알림 발송 인터페이스 — 모든 알림 채널이 구현해야 할 기반 클래스"""

    @abstractmethod
    def send(self, message: str) -> None:
        """알림 메시지 발송"""


class TelegramNotifier(Notifier):
    """텔레그램 봇으로 메시지를 전송하는 알림 클래스"""

    def __init__(self, bot_token: str, chat_id: str):
        self._bot_token = bot_token
        self._chat_id = chat_id

    def send(self, message: str) -> None:
        """텔레그램 봇 API를 통해 메시지 전송"""
        url = TELEGRAM_SEND_MESSAGE_URL.format(token=self._bot_token)
        payload = {
            "chat_id": self._chat_id,
            "text": message,
            "parse_mode": "HTML",
        }
        try:
            resp = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT_SEC)
            resp.raise_for_status()
        except requests.HTTPError as err:
            status = err.response.status_code if err.response is not None else "?"
            if status == 401:
                logger.error("텔레그램 전송 실패: 봇 토큰이 잘못되었습니다 (401)")
            elif status == 400:
                logger.error("텔레그램 전송 실패: chat_id가 잘못되었습니다 (400)")
            else:
                logger.error("텔레그램 전송 실패 (HTTP %s): %s", status, err)
        except Exception as err:
            logger.error("텔레그램 전송 중 오류: %s", err)


class SoundNotifier(Notifier):
    """Windows 시스템 사운드로 알림을 재생하는 클래스 (Mac/Linux에서는 자동 무시)"""

    def __init__(self):
        self._available = self._check_winsound()

    def _check_winsound(self) -> bool:
        """winsound 모듈 사용 가능 여부 확인 (Windows 전용)"""
        try:
            import winsound  # noqa: F401
            return True
        except ImportError:
            return False

    def send(self, message: str) -> None:
        """Windows 알림음 재생 — Mac/Linux에서는 아무것도 하지 않음"""
        if not self._available:
            return
        try:
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception as err:
            logger.warning("사운드 알림 실패: %s", err)


class CompositeNotifier(Notifier):
    """여러 알림 채널을 묶어서 동시에 발송하는 클래스"""

    def __init__(self, notifiers: list[Notifier]):
        self._notifiers = notifiers

    def send(self, message: str) -> None:
        """등록된 모든 알림 채널로 메시지 발송"""
        for notifier in self._notifiers:
            try:
                notifier.send(message)
            except Exception as err:
                logger.error("알림 채널 발송 실패 (%s): %s", type(notifier).__name__, err)


def build_notifier(config: dict) -> CompositeNotifier:
    """
    config.yaml 설정을 읽어 CompositeNotifier 생성.
    텔레그램 토큰/chat_id가 있으면 텔레그램 추가,
    sound.enabled가 true면 사운드 알림 추가.
    """
    notifiers: list[Notifier] = []

    telegram_cfg = config.get("telegram", {})
    bot_token = telegram_cfg.get("bot_token", "")
    chat_id = str(telegram_cfg.get("chat_id", ""))

    placeholder_values = {"여기에_봇토큰_입력", "여기에_챗ID_입력", ""}

    if bot_token not in placeholder_values and chat_id not in placeholder_values:
        notifiers.append(TelegramNotifier(bot_token, chat_id))
    else:
        logger.warning("텔레그램 설정 없음 — 텔레그램 알림 비활성화")

    sound_cfg = config.get("sound", {})
    if sound_cfg.get("enabled", True):
        notifiers.append(SoundNotifier())

    if not notifiers:
        logger.warning(
            "알림 채널이 하나도 활성화되지 않았습니다. config.yaml을 확인하세요."
        )

    return CompositeNotifier(notifiers)
