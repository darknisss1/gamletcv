#!/usr/bin/env python3
"""
Привязка Telegram-уведомлений.

Личный чат: напишите боту /start
Группа: добавьте бота в группу, затем любое сообщение в группе
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests
import yaml


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(path: Path, cfg: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def extract_chat(item: dict) -> tuple[str, str] | None:
    """Вернуть (chat_id, title) из update."""
    msg = item.get("message") or item.get("edited_message") or item.get("channel_post")
    if msg and msg.get("chat"):
        chat = msg["chat"]
        title = chat.get("title") or chat.get("first_name") or str(chat["id"])
        return str(chat["id"]), title

    member = item.get("my_chat_member")
    if member and member.get("chat"):
        chat = member["chat"]
        title = chat.get("title") or chat.get("first_name") or str(chat["id"])
        return str(chat["id"]), title

    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--timeout", type=int, default=180)
    args = parser.parse_args()

    path = Path(args.config)
    cfg = load_config(path)
    tg = cfg.setdefault("alert", {}).setdefault("telegram", {})
    token = tg.get("bot_token") or ""
    if not token:
        print("Сначала укажите bot_token в config.yaml")
        return 1

    print("=== Telegram setup ===")
    print("Ссылка t.me/+... — это приглашение в группу, не chat_id.")
    print()
    print("Для группы:")
    print("  1. Откройте группу по ссылке-приглашению")
    print("  2. Добавьте бота в группу (участники -> добавить)")
    print("  3. Напишите в группе любое сообщение, например: /start")
    print()
    print("Для личных сообщений: просто напишите боту /start")
    print(f"Ожидание до {args.timeout} сек...")

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    offset = None
    deadline = time.time() + args.timeout

    while time.time() < deadline:
        params = {"timeout": 10, "allowed_updates": '["message","edited_message","channel_post","my_chat_member"]'}
        if offset is not None:
            params["offset"] = offset
        resp = requests.get(url, params=params, timeout=25)
        resp.raise_for_status()
        for item in resp.json().get("result", []):
            offset = item["update_id"] + 1
            found = extract_chat(item)
            if not found:
                continue
            chat_id, title = found
            tg["enabled"] = True
            tg["chat_id"] = chat_id
            save_config(path, cfg)
            print(f"Готово: chat_id={chat_id} ({title}) -> {path}")

            test_url = f"https://api.telegram.org/bot{token}/sendMessage"
            requests.post(
                test_url,
                json={"chat_id": chat_id, "text": "Cat Couch Guard: уведомления подключены."},
                timeout=15,
            ).raise_for_status()
            print("Тестовое сообщение отправлено.")
            return 0
        time.sleep(1)

    print("Ничего не пришло. Добавьте бота в группу и напишите там /start, затем запустите снова.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
