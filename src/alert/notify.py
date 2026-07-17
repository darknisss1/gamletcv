"""Уведомления: консоль, звук, Telegram."""

from __future__ import annotations

import logging
import time
from pathlib import Path

import cv2
import requests

logger = logging.getLogger(__name__)


class Alerter:
    def __init__(
        self,
        cooldown_seconds: int = 300,
        beep: bool = True,
        telegram_enabled: bool = False,
        bot_token: str = "",
        chat_id: str = "",
        snapshot_dir: str | Path = "snapshots",
        save_snapshots: bool = True,
    ) -> None:
        self.cooldown_seconds = cooldown_seconds
        self.beep = beep
        self.telegram_enabled = telegram_enabled and bool(bot_token) and bool(chat_id)
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.save_snapshots = save_snapshots
        self.snapshot_dir = Path(snapshot_dir)
        self._last_alert_at = 0.0

        if self.save_snapshots:
            self.snapshot_dir.mkdir(parents=True, exist_ok=True)

    def can_alert(self) -> bool:
        return (time.time() - self._last_alert_at) >= self.cooldown_seconds

    def alert(self, frame, message: str) -> bool:
        if not self.can_alert():
            return False

        self._last_alert_at = time.time()
        logger.warning("ALERT: %s", message)
        print(f"\n*** КОТ НА ДИВАНЕ *** {message}\n")

        snapshot_path = None
        if self.save_snapshots and frame is not None:
            ts = time.strftime("%Y%m%d_%H%M%S")
            snapshot_path = self.snapshot_dir / f"cat_on_couch_{ts}.jpg"
            cv2.imwrite(str(snapshot_path), frame)
            print(f"Снимок: {snapshot_path}")

        if self.beep:
            self._beep()

        if self.telegram_enabled:
            ok = self._send_telegram(message, snapshot_path)
            if ok:
                print("Telegram: отправлено")
            else:
                print("Telegram: ошибка отправки (см. лог)")

        return True

    def _beep(self) -> None:
        try:
            import winsound

            winsound.Beep(880, 400)
            winsound.Beep(660, 400)
        except Exception:  # noqa: BLE001
            print("\a", end="", flush=True)

    def _send_telegram(self, message: str, image_path: Path | None) -> bool:
        if image_path and image_path.exists():
            img = cv2.imread(str(image_path))
            if img is not None:
                h, w = img.shape[:2]
                if w > 1280:
                    scale = 1280 / w
                    img = cv2.resize(img, (1280, int(h * scale)))
                    cv2.imwrite(str(image_path), img)
            try:
                with image_path.open("rb") as photo:
                    resp = requests.post(
                        f"https://api.telegram.org/bot{self.bot_token}/sendPhoto",
                        data={"chat_id": self.chat_id, "caption": message},
                        files={"photo": photo},
                        timeout=30,
                    )
                if resp.ok:
                    return True
                logger.error("Telegram photo error: %s", resp.text)
            except Exception as exc:  # noqa: BLE001
                logger.error("Telegram photo error: %s", exc)

        try:
            resp = requests.post(
                f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                json={"chat_id": self.chat_id, "text": message},
                timeout=30,
            )
            if resp.ok:
                return True
            logger.error("Telegram text error: %s", resp.text)
        except Exception as exc:  # noqa: BLE001
            logger.error("Telegram text error: %s", exc)
        return False

    def _send_telegram_text(self, message: str) -> None:
        self._send_telegram(message, None)

    def _send_telegram_photo(self, message: str, image_path: Path) -> None:
        self._send_telegram(message, image_path)
