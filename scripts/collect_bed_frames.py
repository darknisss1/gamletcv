#!/usr/bin/env python3
"""Снять кадры с RTSP для датасета дивана/матраса (агент или вручную)."""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.camera.ekf import open_capture, resolve_stream
from src.detection.roi import is_frame_valid


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--count", type=int, default=40)
    parser.add_argument("--interval", type=float, default=3.0, help="сек между кадрами")
    parser.add_argument(
        "--out",
        default="dataset/furniture/images/train",
        help="папка для jpg",
    )
    args = parser.parse_args()

    cfg = load_config(ROOT / args.config)
    cam = cfg.get("camera", {})
    stream = resolve_stream(
        host=cam.get("host", ""),
        username=cam.get("username", "admin"),
        password=cam.get("password", "admin"),
        onvif_port=cam.get("onvif_port"),
        rtsp_url=cam.get("rtsp_url") or None,
    )
    out_dir = ROOT / args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = open_capture(stream.rtsp_url)
    if not cap.isOpened():
        print("FAIL: RTSP")
        return 1

    saved = 0
    print("RTSP:", stream.rtsp_url.split("@")[-1])
    print("Сохраняем в", out_dir)

    while saved < args.count:
        ok, frame = cap.read()
        if not ok or frame is None or not is_frame_valid(frame):
            time.sleep(0.2)
            continue
        name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
        path = out_dir / name
        import cv2

        cv2.imwrite(str(path), frame)
        saved += 1
        print(f"[{saved}/{args.count}] {path.name}")
        time.sleep(max(0.0, args.interval))

    cap.release()
    print("Готово. Дальше: python label_furniture.py --images", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
