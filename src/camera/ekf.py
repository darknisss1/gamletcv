"""Подключение к EKF Connect (SCWF-USB и др.) через ONVIF → RTSP."""

from __future__ import annotations

import logging
import os
import re
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import quote, urlparse, urlunparse

import cv2

logger = logging.getLogger(__name__)

# Типичные ONVIF-порты у Tuya/EKF OEM-камер
DEFAULT_ONVIF_PORTS = (80, 8080, 8899, 8000, 554)


@dataclass
class CameraDevice:
    host: str
    onvif_port: int
    name: str = ""


@dataclass
class StreamInfo:
    rtsp_url: str
    host: str
    onvif_port: int
    profile_token: str


def discover_onvif_devices(timeout: int = 5) -> list[CameraDevice]:
    """WS-Discovery в локальной сети (UDP 3702)."""
    try:
        from wsdiscovery import WSDiscovery
        from wsdiscovery.scope import Scope
    except ImportError as exc:
        raise RuntimeError("Установите WSDiscovery: pip install WSDiscovery") from exc

    wsd = WSDiscovery()
    wsd.start()
    try:
        services = wsd.searchServices(
            scopes=[Scope("onvif://www.onvif.org/Profile")],
            timeout=timeout,
        )
        devices: list[CameraDevice] = []
        for svc in services:
            xaddrs = svc.getXAddrs() or []
            if not xaddrs:
                continue
            parsed = urlparse(xaddrs[0])
            if not parsed.hostname:
                continue
            port = parsed.port or 80
            devices.append(
                CameraDevice(
                    host=parsed.hostname,
                    onvif_port=port,
                    name=(svc.getEPR() or "")[:80],
                )
            )
        return devices
    finally:
        wsd.stop()


def _encode_rtsp_credentials(url: str, username: str, password: str) -> str:
    """Вставляет логин/пароль в RTSP URL, если камера вернула URL без auth."""
    parsed = urlparse(url)
    if parsed.username or not username:
        return url
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    user = quote(username, safe="")
    pwd = quote(password, safe="")
    netloc = f"{user}:{pwd}@{host}{port}"
    return urlunparse(
        (parsed.scheme, netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def _wsdl_dir() -> str:
  root = Path(__file__).resolve().parents[2]
  for name in ("wsdl_full", "wsdl"):
    d = root / name
    if d.is_dir() and (d / "devicemgmt.wsdl").exists():
      return str(d)
  return ""


def get_rtsp_url_via_onvif(
    host: str,
    username: str,
    password: str,
    onvif_port: int,
) -> StreamInfo:
    """ONVIF GetProfiles + GetStreamUri — официальный способ для EKF Connect."""
    from onvif import ONVIFCamera

    wsdl = _wsdl_dir()
    cam = ONVIFCamera(host, onvif_port, username, password, wsdl_dir=wsdl or None)
    media = cam.create_media_service()
    profiles = media.GetProfiles()
    if not profiles:
        raise RuntimeError(f"ONVIF на {host}:{onvif_port}: профили потока не найдены")

    # Берём профиль с максимальным разрешением
    profile = max(
        profiles,
        key=lambda p: (
            getattr(getattr(p, "VideoEncoderConfiguration", None), "Resolution", None)
            and (
                p.VideoEncoderConfiguration.Resolution.Width
                * p.VideoEncoderConfiguration.Resolution.Height
            )
        )
        or 0,
    )
    token = profile.token

    req = media.create_type("GetStreamUri")
    req.StreamSetup = {
        "Stream": "RTP-Unicast",
        "Transport": {"Protocol": "RTSP"},
    }
    req.ProfileToken = token
    resp = media.GetStreamUri(req)
    rtsp_url = _encode_rtsp_credentials(resp.Uri, username, password)

    return StreamInfo(
        rtsp_url=rtsp_url,
        host=host,
        onvif_port=onvif_port,
        profile_token=token,
    )


def resolve_stream(
    host: str,
    username: str,
    password: str,
    onvif_port: int | None = None,
    rtsp_url: str | None = None,
) -> StreamInfo:
    """Получить RTSP URL: явный URL или перебор ONVIF-портов."""
    if rtsp_url:
        safe = _encode_rtsp_credentials(rtsp_url, username, password)
        parsed = urlparse(safe)
        return StreamInfo(
            rtsp_url=safe,
            host=parsed.hostname or host,
            onvif_port=onvif_port or 554,
            profile_token="manual",
        )

    ports: Iterable[int] = (onvif_port,) if onvif_port else DEFAULT_ONVIF_PORTS
    errors: list[str] = []

    for port in ports:
        try:
            info = get_rtsp_url_via_onvif(host, username, password, port)
            logger.info("ONVIF OK: %s:%s → %s", host, port, _redact_rtsp(info.rtsp_url))
            return info
        except Exception as exc:  # noqa: BLE001 — перебираем порты
            errors.append(f"{port}: {exc}")

    raise RuntimeError(
        f"Не удалось получить RTSP через ONVIF ({host}). Попытки: {'; '.join(errors)}"
    )


def _redact_rtsp(url: str) -> str:
    return re.sub(r"://([^:]+):([^@]+)@", r"://\1:***@", url)


def open_capture(rtsp_url: str) -> cv2.VideoCapture:
    """
    Открыть RTSP-поток через FFmpeg (OpenCV).

    EKF/Tuya камеры на Windows стабильнее с RTSP over TCP.
    """
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp|stimeout;5000000"
    cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return cap


def probe_stream(rtsp_url: str, read_frames: int = 3) -> tuple[bool, str]:
    """Проверка: поток открывается и отдаёт кадры."""
    cap = open_capture(rtsp_url)
    try:
        if not cap.isOpened():
            return False, "VideoCapture.isOpened() = False"

        ok_count = 0
        last_shape = ""
        for _ in range(read_frames * 5):
            ok, frame = cap.read()
            if ok and frame is not None:
                ok_count += 1
                last_shape = f"{frame.shape[1]}x{frame.shape[0]}"
                if ok_count >= read_frames:
                    return True, f"OK, кадр {last_shape}"
        return False, f"Поток открыт, но кадры не читаются (получено {ok_count})"
    finally:
        cap.release()


def ping_host(host: str, port: int = 80, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False
