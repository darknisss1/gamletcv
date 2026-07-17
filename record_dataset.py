#!/usr/bin/env python3
"""
Сбор кадров с камеры для дообучения YOLO.

  python record_dataset.py
  python record_dataset.py --config config.yaml --out dataset

Клавиши в окне превью:
  s — сохранить кадр (кот на кровати / позитив)
  n — сохранить негатив (кровать без кота)
  q / Esc — выход
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import cv2
import yaml

from src.camera.ekf import open_capture, resolve_stream
from src.detection.bed_zone_io import manual_bed_bbox, use_manual_bed
from src.detection.roi import bed_roi_from_bbox, is_frame_valid


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def read_latest_frame(cap: cv2.VideoCapture, max_grab: int = 6):
    frame = None
    for i in range(max(1, max_grab)):
        if not cap.grab():
            break
        if i == max_grab - 1:
            ok, frame = cap.retrieve()
            if not ok:
                frame = None
    if frame is None:
        ok, frame = cap.read()
        if not ok:
            return None
    return frame


def draw_bed(frame, bed_bbox, roi_padding: float):
    out = frame.copy()
    if not bed_bbox:
        return out
    x1, y1, x2, y2 = bed_bbox
    cv2.rectangle(out, (x1, y1), (x2, y2), (255, 180, 0), 2)
    fh, fw = frame.shape[:2]
    roi = bed_roi_from_bbox(bed_bbox, fw, fh, roi_padding)
    cv2.rectangle(out, (roi.x1, roi.y1), (roi.x2, roi.y2), (0, 200, 255), 1)
    return out


def save_frame(frame, out_dir: Path, tag: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    path = out_dir / f"{stamp}_{tag}.jpg"
    cv2.imwrite(str(path), frame, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="Сбор датасета с камеры")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--out", default="dataset/images")
    parser.add_argument("--roi-padding", type=float, default=None)
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    cam_cfg = cfg.get("camera", {})
    det_cfg = cfg.get("detection", {})
    rt_cfg = cfg.get("runtime", {})
    roi_padding = args.roi_padding
    if roi_padding is None:
        roi_padding = float(det_cfg.get("cat_roi_padding", 0.08))

    bed_bbox = manual_bed_bbox(cfg) if use_manual_bed(cfg) else None
    if not bed_bbox:
        print("Нужна ручная зона кровати: python calibrate_bed.py")
        return 1

    stream = resolve_stream(
        host=cam_cfg.get("host", ""),
        username=cam_cfg.get("username", "admin"),
        password=cam_cfg.get("password", "admin"),
        onvif_port=cam_cfg.get("onvif_port"),
        rtsp_url=cam_cfg.get("rtsp_url") or None,
    )
    cap = open_capture(stream.rtsp_url)
    if not cap.isOpened():
        print("Не удалось открыть RTSP")
        return 1

    pos_dir = Path(args.out) / "cat"
    neg_dir = Path(args.out) / "no_cat"
    flush = int(rt_cfg.get("rtsp_flush_grabs", 6))
    saved_pos = saved_neg = skipped = 0

    print("s = кот на кровати, n = без кота, q = выход")
    try:
        while True:
            frame = read_latest_frame(cap, flush)
            if not is_frame_valid(frame):
                skipped += 1
                continue

            view = draw_bed(frame, bed_bbox, roi_padding)
            cv2.putText(
                view,
                f"cat={saved_pos} no_cat={saved_neg} skip={skipped}",
                (12, 28),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (255, 255, 255),
                2,
            )
            cv2.imshow("Record dataset", view)
            key = cv2.waitKey(1) & 0xFF
            if key in (27, ord("q")):
                break
            if key == ord("s"):
                path = save_frame(frame, pos_dir, "cat")
                saved_pos += 1
                print("saved", path)
            elif key == ord("n"):
                path = save_frame(frame, neg_dir, "no_cat")
                saved_neg += 1
                print("saved", path)
            time.sleep(0.01)
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        cv2.destroyAllWindows()

    print(f"Готово: cat={saved_pos}, no_cat={saved_neg}, пропущено битых кадров={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
