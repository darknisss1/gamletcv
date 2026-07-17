#!/usr/bin/env python3
"""Шаг 1: найти EKF в сети и получить RTSP URL."""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.camera.ekf import (  # noqa: E402
    discover_onvif_devices,
    probe_stream,
    resolve_stream,
)


def load_config(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    parser = argparse.ArgumentParser(description="ONVIF discovery + RTSP для EKF Connect")
    parser.add_argument("--config", default="config.yaml", help="Путь к config.yaml")
    parser.add_argument("--host", help="IP камеры (если discovery не нужен)")
    parser.add_argument("--user", default="admin")
    parser.add_argument("--password", default="")
    parser.add_argument("--onvif-port", type=int, default=None)
    parser.add_argument("--rtsp-url", default="", help="Ручной RTSP URL (из ONVIF Device Manager)")
    parser.add_argument("--no-probe", action="store_true", help="Не проверять чтение кадров")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    cam_cfg = cfg.get("camera", {})

    host = args.host or cam_cfg.get("host") or ""
    username = args.user or cam_cfg.get("username") or "admin"
    password = args.password or cam_cfg.get("password") or ""
    if not password:
        password = getpass.getpass("Пароль камеры (EKF Connect): ")

    onvif_port = args.onvif_port if args.onvif_port is not None else cam_cfg.get("onvif_port")
    rtsp_manual = args.rtsp_url or cam_cfg.get("rtsp_url") or ""

    print("=== 1. Поиск ONVIF-устройств в локальной сети ===")
    try:
        devices = discover_onvif_devices(timeout=5)
        if devices:
            for i, d in enumerate(devices, 1):
                print(f"  [{i}] {d.host}:{d.onvif_port}  {d.name}")
            if not host and len(devices) == 1:
                host = devices[0].host
                if onvif_port is None:
                    onvif_port = devices[0].onvif_port
                print(f"\nАвтовыбор единственной камеры: {host}:{onvif_port}")
        else:
            print("  ONVIF-устройства не найдены (WS-Discovery).")
    except Exception as exc:  # noqa: BLE001
        print(f"  Discovery недоступен: {exc}")

    if not host and not rtsp_manual:
        print(
            "\nУкажите IP камеры из приложения EKF Connect:\n"
            "  python discover.py --host 192.168.1.XXX --password ВАШ_ПАРОЛЬ"
        )
        return 1

    print("\n=== 2. Получение RTSP URL ===")
    try:
        info = resolve_stream(
            host=host or "0.0.0.0",
            username=username,
            password=password,
            onvif_port=onvif_port,
            rtsp_url=rtsp_manual or None,
        )
    except Exception as exc:
        print(f"Ошибка ONVIF: {exc}")
        print(
            "\nОбходной путь:\n"
            "  1. ONVIF Device Manager → Live Video → скопировать RTSP URL\n"
            "  2. python discover.py --rtsp-url \"rtsp://...\" --password ПАРОЛЬ"
        )
        return 1

    redacted = info.rtsp_url
    if "@" in redacted:
        redacted = redacted.split("@", 1)[1]
        redacted = f"rtsp://***:***@{redacted}"
    print(f"  Host:     {info.host}")
    print(f"  ONVIF:    {info.onvif_port}")
    print(f"  Profile:  {info.profile_token}")
    print(f"  RTSP:     {redacted}")

    if args.no_probe:
        return 0

    print("\n=== 3. Проверка потока (OpenCV + FFmpeg, TCP) ===")
    ok, msg = probe_stream(info.rtsp_url)
    print(f"  {'✓' if ok else '✗'} {msg}")

    if ok:
        print(
            "\nГотово. Сохраните в config.yaml:\n"
            f"  camera:\n"
            f"    host: \"{info.host}\"\n"
            f"    onvif_port: {info.onvif_port}\n"
            f"    username: \"{username}\"\n"
            f"    password: \"<ваш пароль>\"\n"
        )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
