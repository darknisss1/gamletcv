#!/usr/bin/env python3
"""Детектор: движение на кровати (+ динамическая зона YOLO)."""

from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

from src.alert.notify import Alerter
from src.camera.ekf import open_capture, resolve_stream
from src.detection.bed_zone_io import manual_bed_bbox, use_manual_bed
from src.detection.furniture import FurnitureTracker, bed_zone_config
from src.detection.cat_lock import CatLockTracker
from src.detection.motion import (
    BedMotionDetector,
    cat_motion_on_bed,
    find_cat_on_bed,
    person_on_bed,
)
from src.detection.yolo_detector import FURNITURE_CLASSES, YoloDetector

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("watch")


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def furniture_ids_from_config(names: list[str] | None) -> set[int]:
    if not names:
        return set(FURNITURE_CLASSES)
    name_to_id = {v: k for k, v in FURNITURE_CLASSES.items()}
    return {name_to_id[n] for n in (names or []) if n in name_to_id} or set(FURNITURE_CLASSES)


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


def overlay_motion_pixels(
    frame: np.ndarray,
    mask: np.ndarray | None,
    alpha: float = 0.5,
    color: tuple[int, int, int] = (255, 0, 255),
) -> np.ndarray:
    """Подсветка движущихся пикселей (без рамок)."""
    if mask is None or cv2.countNonZero(mask) == 0:
        return frame
    out = frame.copy()
    tinted = out.copy()
    tinted[mask > 0] = color
    blend = np.zeros(frame.shape[:2], dtype=np.float32)
    blend[mask > 0] = alpha
    inv = 1.0 - blend
    for c in range(3):
        out[:, :, c] = (tinted[:, :, c] * blend + out[:, :, c] * inv).astype(np.uint8)
    return out


def draw_scene(
    frame,
    bed: FurnitureTracker,
    motion_mask,
    cats,
    active_cat,
    motion_ratio: float,
    stable: int,
    stable_need: int,
    person_nearby: bool,
    motion_pixel_alpha: float = 0.5,
    manual_bed: bool = False,
    cat_reason: str = "",
    locked_cat=None,
):
    out = overlay_motion_pixels(frame, motion_mask, alpha=motion_pixel_alpha)

    if bed.ready and bed.bbox:
        x1, y1, x2, y2 = bed.bbox
        cv2.rectangle(out, (x1, y1), (x2, y2), (255, 180, 0), 2)
        tag = "MANUAL" if manual_bed else f"{bed.confidence:.0%}"
        cv2.putText(
            out,
            f"{bed.label} {tag}",
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 180, 0),
            2,
        )

    # Кот — рамкой; удерживаемый (locked) всегда яркий
    drawn_ids: set[int] = set()
    if locked_cat is not None:
        x1, y1, x2, y2 = locked_cat.bbox
        is_active = active_cat is not None and locked_cat is active_cat
        color = (0, 0, 255)
        if cat_reason == "on_bed":
            color = (0, 140, 255)
        label = "CAT LOCKED"
        if cat_reason == "on_bed":
            label = "CAT ON BED"
        elif cat_reason == "motion":
            label = "CAT MOVING"
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 4)
        cv2.putText(
            out,
            label,
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.75,
            color,
            2,
        )
        drawn_ids.add(id(locked_cat))

    for cat in cats:
        if id(cat) in drawn_ids:
            continue
        x1, y1, x2, y2 = cat.bbox
        is_active = active_cat is not None and cat is active_cat
        color = (0, 0, 255) if is_active else (0, 255, 0)
        if is_active and cat_reason == "on_bed":
            color = (0, 140, 255)
        label = "CAT ON BED!" if is_active and cat_reason == "on_bed" else (
            "CAT MOVING!" if is_active else f"cat {cat.confidence:.0%}"
        )
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 3 if is_active else 2)
        cv2.putText(
            out,
            label,
            (x1, max(y1 - 8, 20)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            color,
            2,
        )

    status = (
        f"{'LOCK ' if locked_cat else ''}cat{'+' + cat_reason if cat_reason else ''} "
        f"stable={stable}/{stable_need}  cats={len(cats)} pixels={motion_ratio:.1%}"
    )
    if person_nearby:
        status += "  person!"
    cv2.putText(out, status, (12, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 2)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Cat on couch guard (motion)")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--no-preview", action="store_true")
    args = parser.parse_args()

    cfg = load_config(Path(args.config))
    cam_cfg = cfg.get("camera", {})
    det_cfg = cfg.get("detection", {})
    mot_cfg = cfg.get("motion", {})
    rt_cfg = cfg.get("runtime", {})
    alert_cfg = cfg.get("alert", {})
    tg_cfg = alert_cfg.get("telegram", {})

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
        logger.error("Не удалось открыть RTSP")
        return 1

    couch_conf = float(det_cfg.get("couch_confidence", 0.10))
    bed_conf = float(det_cfg.get("bed_confidence", couch_conf))
    cat_conf = float(det_cfg.get("cat_confidence", 0.18))
    flush_grabs = int(rt_cfg.get("rtsp_flush_grabs", 6))
    detector = YoloDetector(
        det_cfg.get("yolo_model", "yolo11s.pt"),
        inference_width=int(det_cfg.get("inference_width", 960)),
        furniture_class_ids=furniture_ids_from_config(det_cfg.get("furniture_classes")),
        use_world_model=bool(det_cfg.get("use_world_model", False)),
        enhance=bool(det_cfg.get("enhance_contrast", False)),
    )

    bed_cfg = bed_zone_config(det_cfg)
    bed_tracker = FurnitureTracker(bed_cfg)
    manual_mode = use_manual_bed(cfg)
    manual_bbox = manual_bed_bbox(cfg)
    if manual_mode and manual_bbox:
        bed_tracker.set_manual(manual_bbox)
        logger.info("Зона кровати: ручная разметка bbox=%s", manual_bbox)
    elif manual_mode:
        logger.error(
            "В config указано bed_zone.source: manual, но рамки нет. "
            "Запустите: python calibrate_bed.py"
        )
        return 1

    motion = BedMotionDetector(
        threshold=int(mot_cfg.get("threshold", 30)),
        min_blob_area=int(mot_cfg.get("min_blob_area", 2500)),
        max_blob_area=int(mot_cfg.get("max_blob_area", 200_000)),
        min_bed_overlap=float(mot_cfg.get("min_bed_overlap", 0.45)),
        warmup_frames=int(mot_cfg.get("warmup_frames", 25)),
        erode_iter=int(mot_cfg.get("erode_iter", 2)),
        dilate_iter=int(mot_cfg.get("dilate_iter", 1)),
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
    preview_fps = float(rt_cfg.get("preview_fps", 10))
    preview_interval = 1.0 / preview_fps if preview_fps > 0 else 0.1
    stable_need = int(mot_cfg.get("stable_frames", 2))
    suppress_if_person = bool(mot_cfg.get("suppress_if_person", True))
    person_check_sec = float(mot_cfg.get("person_check_seconds", 5))
    bed_check_sec = float(
        (det_cfg.get("bed_zone") or {}).get(
            "check_interval_seconds",
            det_cfg.get("furniture_check_seconds", 2),
        )
    )
    min_cat_motion_overlap = float(mot_cfg.get("min_cat_motion_overlap", 0.12))
    motion_pixel_alpha = float(mot_cfg.get("pixel_overlay_alpha", 0.5))
    alert_mode = str(mot_cfg.get("alert_mode", "hybrid")).lower()
    if alert_mode not in ("hybrid", "cat_on_bed", "motion_only"):
        alert_mode = "hybrid"
    cat_on_bed_overlap = float(mot_cfg.get("cat_on_bed_overlap", 0.15))
    fluffy_margin = float(det_cfg.get("fluffy_margin", 0.15))
    lock_cfg = mot_cfg.get("cat_lock") or {}
    cat_lock_enabled = bool(lock_cfg.get("enabled", True))
    cat_lock = CatLockTracker(
        release_frames=int(lock_cfg.get("release_frames", 8)),
        grace_frames=int(lock_cfg.get("grace_frames", 2)),
        match_iou=float(lock_cfg.get("match_iou", 0.15)),
        max_center_drift=float(lock_cfg.get("max_center_drift", 180)),
        bed_overlap=cat_on_bed_overlap,
        fluffy_margin=fluffy_margin,
    )

    stable = 0
    last_cats: list = []
    active_cat = None
    last_preview_at = 0.0
    last_person_check = 0.0
    last_bed_check = 0.0
    person_nearby = False

    logger.info(
        "Режим: зона %s, алерт=%s, удержание кота=%s.",
        "ручная" if manual_mode else "YOLO",
        alert_mode,
        "да" if cat_lock_enabled else "нет",
    )

    try:
        while True:
            now = time.monotonic()
            if now - last_preview_at < preview_interval:
                time.sleep(0.005)
                continue

            frame = read_latest_frame(cap, flush_grabs)
            if frame is None:
                logger.warning("Кадр потерян, переподключение...")
                cap.release()
                time.sleep(2)
                cap = open_capture(stream.rtsp_url)
                motion.reset()
                cat_lock.reset()
                stable = 0
                continue

            last_preview_at = now
            fh, fw = frame.shape[:2]

            need_bed = not manual_mode and (
                not bed_tracker.ready or (now - last_bed_check) >= bed_check_sec
            )
            if need_bed:
                dets = detector.detect(
                    frame, cat_conf=0.99, couch_conf=couch_conf, bed_conf=bed_conf
                )
                before = bed_tracker.bbox
                bed_tracker.update(dets.couches, fw, fh)
                last_bed_check = now
                sleepers = [
                    (c.label, round(c.confidence, 2))
                    for c in dets.couches
                    if c.label in ("bed", "couch", "mattress")
                ]
                if bed_tracker.bbox != before or not before:
                    logger.info(
                        "Кровать: picked=%s bbox=%s candidates=%s",
                        bed_tracker.label,
                        bed_tracker.bbox,
                        sleepers or "нет",
                    )
                elif sleepers and not bed_tracker.ready:
                    logger.warning("Есть %s, но кровать не выбрана", sleepers)

            if not bed_tracker.ready:
                if show_preview:
                    cv2.putText(
                        frame,
                        "Ищу кровать...",
                        (12, 28),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.7,
                        (255, 255, 255),
                        2,
                    )
                    cv2.imshow("Cat Couch Guard", resize_preview(frame, preview_max))
                    if (cv2.waitKey(1) & 0xFF) in (27, ord("q")):
                        break
                continue

            if suppress_if_person and (now - last_person_check) >= person_check_sec:
                dets = detector.detect(frame, cat_conf=0.99, couch_conf=0.99)
                person_nearby = person_on_bed(dets.persons, bed_tracker.bbox or (0, 0, 0, 0))
                last_person_check = now

            result = motion.detect(frame, bed_tracker.bbox)  # type: ignore[arg-type]
            fresh_cat = None
            fresh_reason = ""
            last_cats = []
            blocked = suppress_if_person and person_nearby

            need_cat_yolo = not blocked and (
                alert_mode in ("hybrid", "cat_on_bed", "motion_only")
                or cat_lock_enabled
            )
            if need_cat_yolo and (
                alert_mode != "motion_only"
                or result.moving
                or cat_lock.locked
            ):
                dets = detector.detect(frame, cat_conf, couch_conf, bed_conf=bed_conf)
                last_cats = dets.cats
                frame_size = (fw, fh)

                if alert_mode in ("hybrid", "cat_on_bed"):
                    on_bed = find_cat_on_bed(
                        last_cats,
                        bed_tracker.bbox,  # type: ignore[arg-type]
                        min_overlap=cat_on_bed_overlap,
                        fluffy_margin=fluffy_margin,
                        frame_size=frame_size,
                    )
                    if on_bed:
                        fresh_cat = on_bed
                        fresh_reason = "on_bed"

                if alert_mode in ("hybrid", "motion_only") and result.moving:
                    motion_cat = cat_motion_on_bed(
                        last_cats,
                        bed_tracker.bbox,  # type: ignore[arg-type]
                        result.moving,
                        min_motion_overlap=min_cat_motion_overlap,
                    )
                    if motion_cat:
                        fresh_cat = motion_cat
                        fresh_reason = "motion"

            if cat_lock_enabled:
                active_cat = cat_lock.update(
                    bed_tracker.bbox,  # type: ignore[arg-type]
                    last_cats,
                    fresh_cat,
                    fresh_reason,
                    frame_size=(fw, fh),
                )
                cat_reason = cat_lock.reason
            else:
                active_cat = fresh_cat
                cat_reason = fresh_reason

            if active_cat:
                stable += 1
            elif cat_lock.locked:
                stable = max(0, stable - 1)
            else:
                stable = 0

            view = draw_scene(
                frame,
                bed_tracker,
                result.mask,
                last_cats,
                active_cat,
                result.bed_ratio,
                stable,
                stable_need,
                person_nearby,
                motion_pixel_alpha=motion_pixel_alpha,
                manual_bed=manual_mode,
                cat_reason=cat_reason,
                locked_cat=active_cat if cat_lock_enabled and cat_lock.locked else None,
            )

            if stable >= stable_need and alerter.can_alert():
                if cat_reason == "motion":
                    msg = f"Кот двигается на кровати! cat={active_cat.confidence:.0%}"
                else:
                    msg = f"Кот на кровати! cat={active_cat.confidence:.0%}"
                alerter.alert(view, msg)
                stable = 0

            if show_preview:
                cv2.imshow("Cat Couch Guard", resize_preview(view, preview_max))
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

    except KeyboardInterrupt:
        logger.info("Стоп")
    finally:
        cap.release()
        if show_preview:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
