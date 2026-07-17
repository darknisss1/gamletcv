#!/usr/bin/env python3
"""
Разметка границ кровати мышью — один раз, без YOLO.

  python calibrate_bed.py
  python calibrate_bed.py --config config.yaml
  python calibrate_bed.py --image debug_frame.jpg

Управление:
  мышь — выделить прямоугольник (матрас + спинка)
  Enter / s — сохранить в config.yaml
  r — сбросить выделение
  q / Esc — выход без сохранения
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

from src.camera.ekf import open_capture, resolve_stream
from src.detection.bed_zone_io import load_config, write_manual_bed


def load_frame_from_camera(cfg: dict) -> tuple[cv2.Mat | None, str]:
    cam = cfg.get("camera", {})
    stream = resolve_stream(
        host=cam.get("host", ""),
        username=cam.get("username", "admin"),
        password=cam.get("password", "admin"),
        onvif_port=cam.get("onvif_port"),
        rtsp_url=cam.get("rtsp_url") or None,
    )
    cap = open_capture(stream.rtsp_url)
    if not cap.isOpened():
        return None, "не удалось открыть RTSP"

    frame = None
    for _ in range(12):
        if not cap.grab():
            break
        ok, frame = cap.retrieve()
        if not ok:
            frame = None
    if frame is None:
        ok, frame = cap.read()
        if not ok:
            cap.release()
            return None, "кадр с камеры не получен"
    cap.release()
    return frame, stream.rtsp_url.split("@")[-1]


def pick_bed_roi(
    frame,
    max_width: int = 1280,
    window_title: str = "Кровать: выделите рамкой, Enter=сохранить",
) -> tuple[int, int, int, int] | None:
    h, w = frame.shape[:2]
    scale = 1.0
    display = frame
    if w > max_width:
        scale = max_width / w
        display = cv2.resize(frame, (int(w * scale), int(h * scale)))

    print("Выделите кровать мышью. Enter — сохранить, r — заново, Esc — отмена.")
    roi = cv2.selectROI(window_title, display, fromCenter=False, showCrosshair=True)
    cv2.destroyAllWindows()

    x, y, rw, rh = (int(v) for v in roi)
    if rw <= 0 or rh <= 0:
        return None

    if scale != 1.0:
        x = int(x / scale)
        y = int(y / scale)
        rw = int(rw / scale)
        rh = int(rh / scale)

    x1 = max(0, min(x, w - 1))
    y1 = max(0, min(y, h - 1))
    x2 = max(x1 + 1, min(x + rw, w - 1))
    y2 = max(y1 + 1, min(y + rh, h - 1))
    return x1, y1, x2, y2


def preview_bbox(frame, bbox: tuple[int, int, int, int], max_width: int = 1280):
    out = frame.copy()
    x1, y1, x2, y2 = bbox
    cv2.rectangle(out, (x1, y1), (x2, y2), (0, 200, 255), 3)
    cv2.putText(
        out,
        "bed MANUAL",
        (x1, max(y1 - 10, 24)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        (0, 200, 255),
        2,
    )
    h, w = out.shape[:2]
    if w > max_width:
        scale = max_width / w
        out = cv2.resize(out, (int(w * scale), int(h * scale)))
    cv2.imshow("Проверка — любая клавиша", out)
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def main() -> int:
    parser = argparse.ArgumentParser(description="Разметка зоны кровати")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--image", help="Кадр из файла вместо камеры")
    parser.add_argument("--max-width", type=int, default=1280)
    args = parser.parse_args()

    config_path = Path(args.config)
    cfg = load_config(config_path)

    if args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"Не удалось прочитать {args.image}")
            return 1
        source = args.image
    else:
        frame, source = load_frame_from_camera(cfg)
        if frame is None:
            print(source)
            return 1

    fh, fw = frame.shape[:2]
    print(f"Кадр {fw}x{fh} ({source})")

    bbox = pick_bed_roi(frame, max_width=args.max_width)
    if bbox is None:
        print("Отменено.")
        return 1

    print(f"Выбрано: {list(bbox)}")
    preview_bbox(frame, bbox, max_width=args.max_width)

    write_manual_bed(config_path, bbox, frame_size=(fw, fh))
    print(f"Сохранено в {config_path}:")
    print("  detection.bed_zone.source: manual")
    print(f"  detection.bed_zone.manual: {list(bbox)}")
    print(f"  detection.bed_zone.frame_size: [{fw}, {fh}]")
    print()
    print("Запуск: python watch.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
