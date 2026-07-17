#!/usr/bin/env python3
"""Проверка RTSP + рамка дивана (YOLO + bbox_grow). Без GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.camera.ekf import open_capture, resolve_stream
from src.detection.furniture import FurnitureTracker, bed_zone_config
from src.detection.roi import is_frame_valid
from src.detection.yolo_detector import YoloDetector, FURNITURE_CLASSES


def furniture_ids_from_config(names: list[str] | None) -> set[int]:
    if not names:
        return set(FURNITURE_CLASSES)
    name_to_id = {v: k for k, v in FURNITURE_CLASSES.items()}
    return {name_to_id[n] for n in (names or []) if n in name_to_id} or set(FURNITURE_CLASSES)


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.light.yaml")
    parser.add_argument("--frames", type=int, default=8)
    parser.add_argument("--out", default="debug_bed_check.jpg")
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
    print("RTSP:", stream.rtsp_url.split("@")[-1])

    cap = open_capture(stream.rtsp_url)
    if not cap.isOpened():
        print("FAIL: RTSP not opened")
        return 1

    couch_conf = float(det_cfg.get("couch_confidence", 0.08))
    bed_conf = float(det_cfg.get("bed_confidence", 0.06))
    bed_tracker = FurnitureTracker(bed_zone_config(det_cfg))
    zone = det_cfg.get("bed_zone") or {}
    furniture_model_path = det_cfg.get("furniture_yolo_model") or ""
    furniture_detector = None
    detector = None
    if furniture_model_path:
        from src.detection.furniture_yolo import FurnitureYoloDetector

        fpath = Path(furniture_model_path)
        if not fpath.is_absolute():
            fpath = ROOT / fpath
        furniture_detector = FurnitureYoloDetector(
            str(fpath),
            inference_width=int(det_cfg.get("inference_width", 640)),
        )
        print("furniture model:", fpath)
    else:
        detector = YoloDetector(
            det_cfg.get("yolo_model", "yolo11n.pt"),
            inference_width=int(det_cfg.get("inference_width", 640)),
            furniture_class_ids=furniture_ids_from_config(det_cfg.get("furniture_classes")),
            enhance=bool(det_cfg.get("enhance_contrast", False)),
        )
    print(
        "bed_zone: expand_bbox=%s bbox_grow_ratio=%s headboard_lift=%s"
        % (zone.get("expand_bbox"), zone.get("bbox_grow_ratio"), zone.get("headboard_lift_ratio"))
    )

    frame = None
    for _ in range(20):
        ok, frame = cap.read()
        if ok and frame is not None and is_frame_valid(frame):
            break
    cap.release()
    if frame is None:
        print("FAIL: no valid frame")
        return 1

    fh, fw = frame.shape[:2]
    print("frame:", fw, "x", fh)

    if furniture_detector is not None:
        couches = furniture_detector.detect(frame, min_conf=min(couch_conf, bed_conf))
        sleepers = [(c.label, round(c.confidence, 3), c.bbox) for c in couches]
        print("furniture model raw:", sleepers or "none")
        bed_tracker.update(couches, fw, fh)
    else:
        dets = detector.detect(frame, cat_conf=0.99, couch_conf=couch_conf, bed_conf=bed_conf)
        sleepers = [(c.label, round(c.confidence, 3), c.bbox) for c in dets.couches]
        print("YOLO furniture raw:", sleepers or "none")
        bed_tracker.update(dets.couches, fw, fh)
    if not bed_tracker.ready:
        print("FAIL: bed tracker not ready after update")
        return 1

    bx = bed_tracker.bbox
    print("final bbox:", bx, "label:", bed_tracker.label, "conf:", round(bed_tracker.confidence, 3))
    if bx:
        bw, bh = bx[2] - bx[0], bx[3] - bx[1]
        print("bbox size:", bw, "x", bh, "(%.1f%% x %.1f%% of frame)" % (100 * bw / fw, 100 * bh / fh))

    out = frame.copy()
    if bx:
        cv2.rectangle(out, (bx[0], bx[1]), (bx[2], bx[3]), (0, 180, 255), 2)
        cv2.putText(
            out,
            f"{bed_tracker.label} grow={zone.get('bbox_grow_ratio')}",
            (bx[0], max(bx[1] - 8, 16)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 180, 255),
            2,
        )
    out_path = ROOT / args.out
    cv2.imwrite(str(out_path), out)
    print("saved:", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
