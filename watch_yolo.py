#!/usr/bin/env python3
"""
Детектор: кот на кровати через YOLO (без детекции движения).

Запуск:
  python watch_yolo.py
  python watch_yolo.py --config config.yolo.yaml
"""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import cv2
import yaml

from src.alert.notify import Alerter
from src.camera.ekf import open_capture, resolve_stream
from src.detection.bed_zone_io import manual_bed_bbox, use_manual_bed
from src.detection.furniture import FurnitureTracker, bed_zone_config
from src.detection.on_couch import Detection, find_violations
from src.detection.yolo_detector import DEFAULT_FURNITURE_NAMES, FURNITURE_CLASSES, YoloDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("watch_yolo")


def furniture_names_from_config(names: list[str] | None) -> list[str]:
    if not names:
        return list(DEFAULT_FURNITURE_NAMES)
    return names


def furniture_ids_from_config(names: list[str] | None) -> set[int]:
    if not names:
        return set(FURNITURE_CLASSES)
    name_to_id = {v: k for k, v in FURNITURE_CLASSES.items()}
    return {name_to_id[n] for n in names if n in name_to_id} or set(FURNITURE_CLASSES)


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def draw_detections(frame, cats, couches, violations):
    out = frame.copy()
    viol_cat_ids = {id(c) for c, _ in violations}

    for couch in couches:
        x1, y1, x2, y2 = couch.bbox
        cv2.rectangle(out, (x1, y1), (x2, y2), (255, 180, 0), 2)
        cv2.putText(
            out,
            f"{couch.label} {couch.confidence:.0%}",
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 180, 0),
            2,
        )

    for cat in cats:
        x1, y1, x2, y2 = cat.bbox
        on_couch = id(cat) in viol_cat_ids
        color = (0, 0, 255) if on_couch else (0, 255, 0)
        label = "CAT ON COUCH!" if on_couch else f"cat {cat.confidence:.0%}"
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 3 if on_couch else 2)
        cv2.putText(
            out,
            label,
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )
    return out


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


def resize_preview(frame, max_width: int):
    h, w = frame.shape[:2]
    if w <= max_width:
        return frame
    scale = max_width / w
    return cv2.resize(frame, (max_width, int(h * scale)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Cat on couch guard (YOLO only)")
    parser.add_argument("--config", default="config.yolo.yaml")
    parser.add_argument("--no-preview", action="store_true")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    cam_cfg = cfg.get("camera", {})
    det_cfg = cfg.get("detection", {})
    rt_cfg = cfg.get("runtime", {})
    alert_cfg = cfg.get("alert", {})
    tg_cfg = alert_cfg.get("telegram", {})

    logger.info("Подключение к камере...")
    stream = resolve_stream(
        host=cam_cfg.get("host", ""),
        username=cam_cfg.get("username", "admin"),
        password=cam_cfg.get("password", "admin"),
        onvif_port=cam_cfg.get("onvif_port"),
        rtsp_url=cam_cfg.get("rtsp_url") or None,
    )
    logger.info("RTSP: %s", stream.rtsp_url.split("@")[-1])

    cap = open_capture(stream.rtsp_url)
    if not cap.isOpened():
        logger.error("Не удалось открыть RTSP поток")
        return 1

    detector = YoloDetector(
        det_cfg.get("yolo_model", "yolo11s.pt"),
        inference_width=int(det_cfg.get("inference_width", 960)),
        furniture_class_ids=furniture_ids_from_config(det_cfg.get("furniture_classes")),
        furniture_names=furniture_names_from_config(det_cfg.get("furniture_classes")),
        world_model=det_cfg.get("world_model", "yolov8s-worldv2.pt"),
        use_world_model=bool(det_cfg.get("use_world_model", False)),
        enhance=bool(det_cfg.get("enhance_contrast", False)),
    )
    alerter = Alerter(
        cooldown_seconds=int(alert_cfg.get("cooldown_seconds", 10)),
        beep=bool(alert_cfg.get("beep", True)),
        telegram_enabled=bool(tg_cfg.get("enabled", False)),
        bot_token=tg_cfg.get("bot_token", ""),
        chat_id=str(tg_cfg.get("chat_id", "")),
        snapshot_dir=rt_cfg.get("snapshot_dir", "snapshots"),
        save_snapshots=bool(rt_cfg.get("save_snapshots", True)),
    )

    show_preview = bool(rt_cfg.get("show_preview", True)) and not args.no_preview
    preview_max = int(rt_cfg.get("preview_max_width", 960))
    preview_fps = float(rt_cfg.get("preview_fps", 8))
    preview_interval = 1.0 / preview_fps if preview_fps > 0 else 0.125
    rtsp_flush_grabs = int(rt_cfg.get("rtsp_flush_grabs", 6))
    stable_need = int(det_cfg.get("stable_frames", 1))
    min_overlap = float(det_cfg.get("overlap_ratio", 0.18))
    fluffy_margin = float(det_cfg.get("fluffy_margin", 0.15))
    cat_conf = float(det_cfg.get("cat_confidence", 0.18))
    couch_conf = float(det_cfg.get("couch_confidence", 0.10))
    bed_conf = float(det_cfg.get("bed_confidence", couch_conf))
    check_interval = float(det_cfg.get("check_interval_seconds", 1.5))

    bed_cfg = bed_zone_config(det_cfg)
    furniture_tracker = FurnitureTracker(bed_cfg)
    manual_mode = use_manual_bed(cfg)
    manual_bbox = manual_bed_bbox(cfg)
    manual_couch: list[Detection] = []
    if manual_mode and manual_bbox:
        manual_couch = [Detection("bed", 1.0, manual_bbox)]
        logger.info("Зона кровати: ручная разметка bbox=%s", manual_bbox)
    elif manual_mode:
        logger.error("Запустите: python calibrate_bed.py")
        return 1

    stable_count = 0
    frame_no = 0
    last_check_at = 0.0
    last_dets = None
    last_couches: list = []
    last_violations: list = []
    last_view = None
    last_preview_at = 0.0

    mode = "YOLO-World" if detector.use_world_model else "YOLO"
    logger.info(
        "Режим %s: кот + %s, проверка раз в %.1f с. Telegram=%s.",
        mode,
        "ручная зона" if manual_mode else "кровать YOLO",
        check_interval,
        "да" if alerter.telegram_enabled else "нет",
    )

    try:
        while True:
            now = time.monotonic()
            need_check = now - last_check_at >= check_interval
            need_preview = show_preview and (now - last_preview_at >= preview_interval)

            if not need_check and not need_preview:
                time.sleep(0.02)
                continue

            frame = read_latest_frame(cap, rtsp_flush_grabs)
            if frame is None:
                logger.warning("Кадр не получен, переподключение через 2 сек...")
                cap.release()
                time.sleep(2)
                cap = open_capture(stream.rtsp_url)
                stable_count = 0
                continue

            frame_no += 1

            if need_check:
                last_check_at = now
                last_dets = detector.detect(frame, cat_conf, couch_conf, bed_conf=bed_conf)
                fh, fw = frame.shape[:2]
                if manual_mode:
                    last_couches = manual_couch
                else:
                    last_couches = furniture_tracker.update(last_dets.couches, fw, fh)
                last_violations = find_violations(
                    last_dets.cats,
                    last_couches,
                    min_overlap,
                    fluffy_margin=fluffy_margin,
                    frame_size=(fw, fh),
                )

                if last_violations:
                    stable_count += 1
                    if stable_count >= stable_need and alerter.can_alert():
                        cat, couch = last_violations[0]
                        msg = (
                            f"Кот на диване! "
                            f"cat={cat.confidence:.0%}, couch={couch.confidence:.0%}"
                        )
                        last_view = draw_detections(
                            frame, last_dets.cats, last_couches, last_violations
                        )
                        alerter.alert(last_view, msg)
                else:
                    stable_count = 0

                status = (
                    f"stable={stable_count}/{stable_need}  "
                    f"cats={len(last_dets.cats)}  couches={len(last_couches)}  "
                    f"infer={last_dets.inference_ms:.0f}ms"
                )
                last_view = draw_detections(
                    frame, last_dets.cats, last_couches, last_violations
                )
                cv2.putText(
                    last_view,
                    status,
                    (12, 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.65,
                    (255, 255, 255),
                    2,
                )

            if need_preview and last_view is not None:
                cv2.imshow("Cat Couch Guard (YOLO)", resize_preview(last_view, preview_max))
                last_preview_at = now
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

            if frame_no % 30 == 0 and last_dets is not None:
                logger.info(
                    "кадр %d | cats=%d couches=%d | infer %.0f ms",
                    frame_no,
                    len(last_dets.cats),
                    len(last_couches),
                    last_dets.inference_ms,
                )

    except KeyboardInterrupt:
        logger.info("Остановка по Ctrl+C")
    finally:
        cap.release()
        if show_preview:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
