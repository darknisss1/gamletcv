"""Удержание кота в кадре: поймали — не отпускаем, пока не уйдёт с кровати."""

from __future__ import annotations

import time

from src.detection.on_couch import BBox, Detection, bbox_area, cat_on_couch, intersection_area


def bbox_iou(a: BBox, b: BBox) -> float:
    inter = intersection_area(a, b)
    if inter <= 0:
        return 0.0
    union = bbox_area(a) + bbox_area(b) - inter
    return inter / union if union > 0 else 0.0


def bbox_center(box: BBox) -> tuple[float, float]:
    x1, y1, x2, y2 = box
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def center_distance(a: BBox, b: BBox) -> float:
    ax, ay = bbox_center(a)
    bx, by = bbox_center(b)
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


class CatLockTracker:
    """
    Поймали кота на кровати — держим рамку в кадре.
    Сброс, когда YOLO не видит кота на кровати несколько кадров подряд.
    """

    def __init__(
        self,
        release_frames: int = 8,
        grace_frames: int = 2,
        match_iou: float = 0.15,
        max_center_drift: float = 180.0,
        bed_overlap: float = 0.15,
        fluffy_margin: float = 0.15,
    ) -> None:
        self.release_frames = release_frames
        self.grace_frames = grace_frames
        self.match_iou = match_iou
        self.max_center_drift = max_center_drift
        self.bed_overlap = bed_overlap
        self.fluffy_margin = fluffy_margin
        self._locked: Detection | None = None
        self._reason: str = ""
        self._gone_frames = 0
        self._locked_at = 0.0

    @property
    def locked(self) -> bool:
        return self._locked is not None and self._gone_frames < self.release_frames

    @property
    def reason(self) -> str:
        return self._reason if self.locked else ""

    def reset(self) -> None:
        self._locked = None
        self._reason = ""
        self._gone_frames = 0

    def _is_on_bed(
        self,
        cat: Detection,
        bed: BBox,
        frame_size: tuple[int, int] | None,
    ) -> bool:
        return cat_on_couch(
            cat.bbox,
            bed,
            min_overlap=self.bed_overlap,
            fluffy_margin=self.fluffy_margin,
            frame_size=frame_size,
        )

    def _cats_on_bed(
        self,
        cats: list[Detection],
        bed: BBox,
        frame_size: tuple[int, int] | None,
    ) -> list[Detection]:
        return [c for c in cats if self._is_on_bed(c, bed, frame_size)]

    def _match_on_bed(
        self,
        cats_on_bed: list[Detection],
    ) -> Detection | None:
        if not self._locked or not cats_on_bed:
            return None
        ref = self._locked.bbox
        best: Detection | None = None
        best_score = -1.0
        for cat in cats_on_bed:
            iou = bbox_iou(ref, cat.bbox)
            dist = center_distance(ref, cat.bbox)
            if iou < self.match_iou and dist > self.max_center_drift:
                continue
            score = iou * 2.0 + cat.confidence
            if score > best_score:
                best = cat
                best_score = score
        return best

    def _pick_on_bed(
        self,
        cats_on_bed: list[Detection],
        preferred: Detection | None,
    ) -> Detection | None:
        if preferred and preferred in cats_on_bed:
            return preferred
        if not cats_on_bed:
            return None
        return max(cats_on_bed, key=lambda c: c.confidence)

    def update(
        self,
        bed: BBox,
        yolo_cats: list[Detection],
        candidate: Detection | None,
        candidate_reason: str,
        frame_size: tuple[int, int] | None = None,
    ) -> Detection | None:
        cats_on_bed = self._cats_on_bed(yolo_cats, bed, frame_size)
        verified_candidate = (
            candidate
            if candidate is not None and self._is_on_bed(candidate, bed, frame_size)
            else None
        )

        if self._locked is None:
            pick = self._pick_on_bed(cats_on_bed, verified_candidate)
            if pick is not None:
                self._locked = pick
                self._reason = candidate_reason or "on_bed"
                self._locked_at = time.monotonic()
                self._gone_frames = 0
            return pick

        matched = self._match_on_bed(cats_on_bed)
        confirmed = self._pick_on_bed(cats_on_bed, matched or verified_candidate)

        if confirmed is not None:
            self._locked = confirmed
            self._gone_frames = 0
            if candidate_reason:
                self._reason = candidate_reason
            elif matched:
                self._reason = "locked"
            return confirmed

        self._gone_frames += 1
        if self._gone_frames >= self.release_frames:
            self.reset()
            return None

        # Короткая пауза YOLO — держим рамку, но не «вечный призрак»
        if self._gone_frames <= self.grace_frames and self._locked is not None:
            return self._locked
        return None
