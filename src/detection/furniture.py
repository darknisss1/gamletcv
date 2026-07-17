"""Нормализация дивана/кровати — YOLO часто видит только матрас или спинку."""

from __future__ import annotations

import time
from dataclasses import dataclass

from src.detection.on_couch import BBox, Detection


@dataclass(frozen=True)
class BedZoneConfig:
    """Параметры рамки кровати: динамическая, без захода на стену."""

    headboard_up_ratio: float = 1.15
    pad_down_ratio: float = 0.12
    pad_x_ratio: float = 0.02
    wall_top_percent: float = 38.0
    hold_seconds: float = 4.0


def bed_zone_config(det_cfg: dict) -> BedZoneConfig:
    zone = det_cfg.get("bed_zone") or {}
    return BedZoneConfig(
        headboard_up_ratio=float(zone.get("headboard_up_ratio", 1.15)),
        pad_down_ratio=float(zone.get("pad_down_ratio", 0.12)),
        pad_x_ratio=float(zone.get("pad_x_ratio", 0.02)),
        wall_top_percent=float(zone.get("wall_top_percent", 38)),
        hold_seconds=float(
            zone.get("hold_seconds", det_cfg.get("furniture_hold_seconds", 4))
        ),
    )


BED_LABELS = frozenset({"bed", "couch", "mattress"})
LABEL_PRIORITY = {"bed": 2.5, "couch": 2.2, "mattress": 2.0}


def bbox_area(box: BBox) -> int:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def expand_bed_zone(
    det: Detection,
    frame_w: int,
    frame_h: int,
    cfg: BedZoneConfig,
) -> Detection:
    """
    Чуть расширить YOLO-рамку: матрас + спинка.
    Вверх ограничен wall_top — рамка не залезает на стену.
    """
    x1, y1, x2, y2 = det.bbox
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return det

    wall_top = int(frame_h * cfg.wall_top_percent / 100.0)
    pad_x = int(w * cfg.pad_x_ratio)

    # Узкая полоса — YOLO видел в основном матрас, тянем вверх на спинку
    if h < w * 0.45:
        pad_up = int(h * cfg.headboard_up_ratio)
        pad_down = int(h * cfg.pad_down_ratio)
    else:
        pad_up = int(h * 0.08)
        pad_down = int(h * cfg.pad_down_ratio)

    x1 = max(0, x1 - pad_x)
    x2 = min(frame_w - 1, x2 + pad_x)
    y1 = max(wall_top, y1 - pad_up)
    y2 = min(frame_h - 1, y2 + pad_down)
    return Detection(det.label, det.confidence, (x1, y1, x2, y2))


def expand_partial_furniture(
    det: Detection,
    frame_w: int,
    frame_h: int,
    cfg: BedZoneConfig,
) -> Detection:
    if det.label in ("bed", "couch", "mattress"):
        return expand_bed_zone(det, frame_w, frame_h, cfg)
    return det


def merge_bed_parts(couches: list[Detection]) -> list[Detection]:
    """Если YOLO видит матрас и спинку отдельно — склеить в одну рамку."""
    beds = [c for c in couches if c.label in ("bed", "couch", "mattress")]
    rest = [c for c in couches if c.label not in ("bed", "couch", "mattress")]
    if len(beds) <= 1:
        return couches

    def x_overlap(a: Detection, b: Detection) -> float:
        ax1, _, ax2, _ = a.bbox
        bx1, _, bx2, _ = b.bbox
        inter = max(0, min(ax2, bx2) - max(ax1, bx1))
        union = max(ax2, bx2) - min(ax1, bx1)
        return inter / union if union > 0 else 0.0

    groups: list[list[Detection]] = []
    for bed in sorted(beds, key=lambda d: d.bbox[1]):
        placed = False
        for group in groups:
            if any(x_overlap(bed, g) >= 0.25 for g in group):
                group.append(bed)
                placed = True
                break
        if not placed:
            groups.append([bed])

    merged_beds: list[Detection] = []
    for group in groups:
        x1 = min(g.bbox[0] for g in group)
        y1 = min(g.bbox[1] for g in group)
        x2 = max(g.bbox[2] for g in group)
        y2 = max(g.bbox[3] for g in group)
        conf = max(g.confidence for g in group)
        label = max(group, key=lambda g: g.confidence).label
        merged_beds.append(Detection(label, conf, (x1, y1, x2, y2)))

    return merged_beds + rest


def pick_main_furniture(
    couches: list[Detection],
    frame_w: int,
    frame_h: int,
    cfg: BedZoneConfig,
) -> list[Detection]:
    """Главная кровать/диван — никогда стул и прочая мебель."""
    sleepers = [c for c in couches if c.label in BED_LABELS]
    if not sleepers:
        return []

    merged = merge_bed_parts(sleepers)
    expanded = [expand_partial_furniture(c, frame_w, frame_h, cfg) for c in merged]

    def score(d: Detection) -> float:
        x1, y1, x2, y2 = d.bbox
        w, h = x2 - x1, y2 - y1
        cy = (y1 + y2) / 2
        if cy < frame_h * 0.20:
            return 0.0
        if cy > frame_h * 0.98:
            return 0.0
        priority = LABEL_PRIORITY.get(d.label, 1.0)
        aspect = 1.15 if w > h * 1.2 else 1.0
        return bbox_area(d.bbox) * d.confidence * priority * aspect

    best = max(expanded, key=score)
    if score(best) <= 0:
        return []
    return [best]


class FurnitureTracker:
    """Динамическая рамка кровати; при промахе YOLO держим последнюю."""

    def __init__(self, cfg: BedZoneConfig) -> None:
        self.cfg = cfg
        self._last: Detection | None = None
        self._last_at: float = 0.0

    @property
    def ready(self) -> bool:
        return self._last is not None

    @property
    def bbox(self) -> BBox | None:
        return self._last.bbox if self._last else None

    @property
    def label(self) -> str:
        return self._last.label if self._last else "bed"

    @property
    def confidence(self) -> float:
        return self._last.confidence if self._last else 0.0

    def set_manual(self, bbox: BBox, label: str = "bed") -> None:
        self._last = Detection(label, 1.0, bbox)
        self._last_at = time.monotonic()

    def update(self, couches: list[Detection], frame_w: int, frame_h: int) -> list[Detection]:
        picked = pick_main_furniture(couches, frame_w, frame_h, self.cfg)
        now = time.monotonic()

        if picked:
            new = picked[0]
            if (
                self._last
                and self._last.label in BED_LABELS
                and new.label in BED_LABELS
                and new.confidence < self._last.confidence * 0.55
            ):
                # Не прыгать на слабый детект, пока старый ещё свежий
                if (now - self._last_at) <= self.cfg.hold_seconds:
                    return [
                        Detection(
                            self._last.label,
                            self._last.confidence,
                            self._last.bbox,
                        )
                    ]
            self._last = new
            self._last_at = now
            return picked

        if self._last and (now - self._last_at) <= self.cfg.hold_seconds:
            stale = Detection(
                f"{self._last.label}?",
                self._last.confidence * 0.5,
                self._last.bbox,
            )
            return [stale]

        return []
