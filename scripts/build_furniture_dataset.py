#!/usr/bin/env python3
"""
Сбор кадров + авто-разметка (фиксированная камера).
daybed — эталонная рамка; mattress — YOLO COCO bed на каждом кадре.
"""

from __future__ import annotations

import argparse
import random
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.camera.ekf import open_capture, resolve_stream
from src.detection.furniture import bed_zone_config
from src.detection.on_couch import Detection
from src.detection.roi import is_frame_valid
from src.detection.yolo_detector import YoloDetector, FURNITURE_CLASSES


def furniture_ids_from_config(names: list[str] | None) -> set[int]:
    if not names:
        return set(FURNITURE_CLASSES)
    name_to_id = {v: k for k, v in FURNITURE_CLASSES.items()}
    return {name_to_id[n] for n in (names or []) if n in name_to_id} or set(FURNITURE_CLASSES)


# Ручная калибровка комнаты (2304×1296, поток 101)
REF_DAYBED = (520, 608, 1627, 1214)
REF_SIZE = (2304, 1296)


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def yolo_line(cls_id: int, box: tuple[int, int, int, int], w: int, h: int) -> str:
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2) / w
    cy = ((y1 + y2) / 2) / h
    bw = (x2 - x1) / w
    bh = (y2 - y1) / h
    return f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def scale_box(
    box: tuple[int, int, int, int],
    from_size: tuple[int, int],
    to_size: tuple[int, int],
) -> tuple[int, int, int, int]:
    fw, fh = from_size
    tw, th = to_size
    sx, sy = tw / fw, th / fh
    x1, y1, x2, y2 = box
    return (
        int(round(x1 * sx)),
        int(round(y1 * sy)),
        int(round(x2 * sx)),
        int(round(y2 * sy)),
    )


def clip_box(box: tuple[int, int, int, int], w: int, h: int) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    return (
        max(0, min(x1, w - 1)),
        max(0, min(y1, h - 1)),
        max(0, min(x2, w - 1)),
        max(0, min(y2, h - 1)),
    )


def best_mattress_raw(couches: list[Detection]) -> tuple[int, int, int, int] | None:
    beds = [c for c in couches if c.label in ("bed", "couch", "mattress")]
    if not beds:
        return None
    best = max(beds, key=lambda c: c.confidence)
    return best.bbox


def fallback_mattress(daybed: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
    x1, y1, x2, y2 = daybed
    w, h = x2 - x1, y2 - y1
    return (
        x1 + int(w * 0.06),
        y1 + int(h * 0.28),
        x2 - int(w * 0.04),
        y2 - int(h * 0.06),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--count", type=int, default=36)
    parser.add_argument("--interval", type=float, default=2.5)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    args = parser.parse_args()

    cfg = load_config(ROOT / args.config)
    cam = cfg.get("camera", {})
    det_cfg = cfg.get("detection", {})
    stream = resolve_stream(
        host=cam.get("host", ""),
        username=cam.get("username", "admin"),
        password=cam.get("password", "admin"),
        onvif_port=cam.get("onvif_port"),
        rtsp_url=cam.get("rtsp_url") or None,
    )

    base = ROOT / "dataset" / "furniture"
    for sub in ("images/train", "images/val", "labels/train", "labels/val"):
        (base / sub).mkdir(parents=True, exist_ok=True)

    detector = YoloDetector(
        det_cfg.get("yolo_model", "yolo11s.pt"),
        inference_width=int(det_cfg.get("inference_width", 960)),
        furniture_class_ids=furniture_ids_from_config(det_cfg.get("furniture_classes")),
    )
    couch_conf = float(det_cfg.get("couch_confidence", 0.1))
    bed_conf = float(det_cfg.get("bed_confidence", 0.08))

    cap = open_capture(stream.rtsp_url)
    if not cap.isOpened():
        print("FAIL: RTSP")
        return 1

    records: list[tuple[str, tuple[int, int, int, int], tuple[int, int, int, int]]] = []
    print("RTSP:", stream.rtsp_url.split("@")[-1])

    saved = 0
    while saved < args.count:
        ok, frame = cap.read()
        if not ok or frame is None or not is_frame_valid(frame):
            time.sleep(0.15)
            continue
        fh, fw = frame.shape[:2]
        daybed = scale_box(REF_DAYBED, REF_SIZE, (fw, fh))
        daybed = clip_box(daybed, fw, fh)

        dets = detector.detect(frame, cat_conf=0.99, couch_conf=couch_conf, bed_conf=bed_conf)
        matt = best_mattress_raw(dets.couches)
        if matt is None:
            matt = fallback_mattress(daybed)
        matt = clip_box(matt, fw, fh)

        name = datetime.now().strftime("%Y%m%d_%H%M%S_%f") + ".jpg"
        tmp_path = base / "images" / "train" / name
        cv2.imwrite(str(tmp_path), frame)
        records.append((name, daybed, matt))
        saved += 1
        print(f"[{saved}/{args.count}] {name}")
        time.sleep(max(0.0, args.interval))

    cap.release()

    random.seed(42)
    random.shuffle(records)
    n_val = max(1, int(len(records) * args.val_ratio))
    val_set = {r[0] for r in records[:n_val]}

    for name, daybed, matt in records:
        split = "val" if name in val_set else "train"
        img_src = base / "images" / "train" / name
        if split == "val":
            img_src.rename(base / "images" / "val" / name)

        img_path = base / "images" / split / name
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        fh, fw = frame.shape[:2]
        lines = [
            yolo_line(0, daybed, fw, fh),
            yolo_line(1, matt, fw, fh),
        ]
        (base / "labels" / split / (Path(name).stem + ".txt")).write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )

    data_yaml = ROOT / "data" / "furniture.yaml"
    data_yaml.write_text(
        "path: dataset/furniture\ntrain: images/train\nval: images/val\n\n"
        "names:\n  0: daybed\n  1: mattress\n",
        encoding="utf-8",
    )
    print("dataset:", base)
    print("data:", data_yaml)
    print("val images:", len(list((base / "images" / "val").glob('*.jpg'))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
