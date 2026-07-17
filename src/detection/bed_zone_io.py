"""Загрузка и сохранение ручной зоны кровати в config.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.detection.on_couch import BBox


def load_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def save_config(path: Path, cfg: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)


def bed_zone_section(cfg: dict) -> dict:
    det = cfg.setdefault("detection", {})
    zone = det.setdefault("bed_zone", {})
    if not isinstance(zone, dict):
        zone = {}
        det["bed_zone"] = zone
    return zone


def manual_bed_bbox(cfg: dict) -> BBox | None:
    zone = (cfg.get("detection") or {}).get("bed_zone") or {}
    manual = zone.get("manual")
    if manual and len(manual) == 4:
        return tuple(int(v) for v in manual)  # type: ignore[return-value]
    return None


def bed_zone_source(cfg: dict) -> str:
    zone = (cfg.get("detection") or {}).get("bed_zone") or {}
    source = str(zone.get("source", "yolo")).lower()
    if source not in ("manual", "yolo"):
        return "yolo"
    if source == "manual" and manual_bed_bbox(cfg) is None:
        return "yolo"
    return source


def use_manual_bed(cfg: dict) -> bool:
    return bed_zone_source(cfg) == "manual"


def write_manual_bed(
    config_path: Path,
    bbox: BBox,
    frame_size: tuple[int, int] | None = None,
) -> None:
    if config_path.exists():
        cfg = load_config(config_path)
    else:
        cfg = {}
    zone = bed_zone_section(cfg)
    zone["source"] = "manual"
    zone["manual"] = [int(bbox[0]), int(bbox[1]), int(bbox[2]), int(bbox[3])]
    if frame_size:
        zone["frame_size"] = [int(frame_size[0]), int(frame_size[1])]
    save_config(config_path, cfg)
