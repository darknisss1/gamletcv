"""Движение на статичной кровати: ищем движущиеся объекты в зоне bed."""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from src.detection.on_couch import BBox, Detection, bbox_area, intersection_area


@dataclass
class MovingObject:
    bbox: BBox
    area: int
    overlap_bed: float  # доля bbox внутри кровати


@dataclass
class BedMotionResult:
    moving: list[MovingObject]
    bed_ratio: float
    has_bed_motion: bool
    mask: np.ndarray | None = None


@dataclass
class StaticBedZone:
    """Зафиксированная зона кровати — не прыгает каждый кадр."""

    bbox: BBox | None = None
    label: str = "bed"
    confidence: float = 0.0

    def lock(self, det: Detection) -> None:
        self.bbox = det.bbox
        self.label = det.label
        self.confidence = det.confidence

    @property
    def ready(self) -> bool:
        return self.bbox is not None


class BedMotionDetector:
    """
    Фон статичен (кровать), движется только объект (кот).
    MOG2 + контуры внутри ROI кровати.
    """

    def __init__(
        self,
        threshold: int = 25,
        blur_size: int = 21,
        min_blob_area: int = 600,
        max_blob_area: int = 200_000,
        min_bed_overlap: float = 0.35,
        min_bed_motion_ratio: float = 0.008,
        history: int = 120,
        warmup_frames: int = 25,
        dilate_iter: int = 1,
        erode_iter: int = 2,
    ) -> None:
        self.threshold = threshold
        self.blur_size = blur_size | 1
        self.min_blob_area = min_blob_area
        self.max_blob_area = max_blob_area
        self.min_bed_overlap = min_bed_overlap
        self.min_bed_motion_ratio = min_bed_motion_ratio
        self.warmup_frames = warmup_frames
        self.dilate_iter = dilate_iter
        self.erode_iter = erode_iter
        self._frame_i = 0
        self._kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        self._kernel_big = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=history,
            varThreshold=16,
            detectShadows=False,
        )
        self._prev_gray: np.ndarray | None = None

    def reset(self) -> None:
        self._frame_i = 0
        self._prev_gray = None
        self._bg = cv2.createBackgroundSubtractorMOG2(
            history=120,
            varThreshold=16,
            detectShadows=False,
        )

    def _roi_mask(self, shape: tuple[int, ...], bed: BBox) -> np.ndarray:
        h, w = shape[:2]
        mask = np.zeros((h, w), dtype=np.uint8)
        x1, y1, x2, y2 = bed
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w, x2), min(h, y2)
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 255
        return mask

    def _motion_mask(self, frame: np.ndarray, bed_mask: np.ndarray) -> np.ndarray:
        fg = self._bg.apply(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (self.blur_size, self.blur_size), 0)

        diff_mask = np.zeros_like(fg)
        if self._prev_gray is not None:
            diff = cv2.absdiff(self._prev_gray, gray)
            _, diff_mask = cv2.threshold(diff, self.threshold, 255, cv2.THRESH_BINARY)
        self._prev_gray = gray

        # MOG2 + diff: ловим и медленное ползание, и резкий прыжок
        combined = cv2.bitwise_or(fg, diff_mask)
        combined = cv2.bitwise_and(combined, bed_mask)
        if self.erode_iter > 0:
            combined = cv2.erode(combined, self._kernel, iterations=self.erode_iter)
        if self.dilate_iter > 0:
            combined = cv2.dilate(combined, self._kernel_big, iterations=self.dilate_iter)
        return combined

    @staticmethod
    def _blob_overlap_bed(blob: BBox, bed: BBox) -> float:
        b_area = bbox_area(blob)
        if b_area == 0:
            return 0.0
        return intersection_area(blob, bed) / b_area

    def detect(self, frame: np.ndarray, bed: BBox) -> BedMotionResult:
        self._frame_i += 1
        bed_mask = self._roi_mask(frame.shape, bed)
        mask = self._motion_mask(frame, bed_mask)

        if self._frame_i <= self.warmup_frames:
            return BedMotionResult(moving=[], bed_ratio=0.0, has_bed_motion=False, mask=mask)

        bed_pixels = max(1, cv2.countNonZero(bed_mask))
        bed_ratio = cv2.countNonZero(mask) / bed_pixels

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        moving: list[MovingObject] = []
        for contour in contours:
            area = int(cv2.contourArea(contour))
            if area < self.min_blob_area or area > self.max_blob_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            bbox = (x, y, x + w, y + h)
            overlap = self._blob_overlap_bed(bbox, bed)
            if overlap < self.min_bed_overlap:
                continue
            moving.append(MovingObject(bbox=bbox, area=area, overlap_bed=overlap))

        has_bed_motion = bool(moving)
        return BedMotionResult(
            moving=moving,
            bed_ratio=bed_ratio,
            has_bed_motion=has_bed_motion,
            mask=mask,
        )


def person_on_bed(persons: list[Detection], bed: BBox, min_overlap: float = 0.2) -> bool:
    for person in persons:
        p_area = bbox_area(person.bbox)
        if p_area == 0:
            continue
        if intersection_area(person.bbox, bed) / p_area >= min_overlap:
            return True
    return False


def find_cat_on_bed(
    cats: list[Detection],
    bed: BBox,
    min_overlap: float = 0.15,
    fluffy_margin: float = 0.15,
    frame_size: tuple[int, int] | None = None,
) -> Detection | None:
    """Кот лежит/сидит на кровати — без требования движения."""
    from src.detection.on_couch import cat_on_couch, overlap_ratio

    best: Detection | None = None
    best_score = 0.0
    for cat in cats:
        if not cat_on_couch(
            cat.bbox, bed, min_overlap=min_overlap, fluffy_margin=fluffy_margin, frame_size=frame_size
        ):
            continue
        score = overlap_ratio(cat.bbox, bed) * cat.confidence
        if score > best_score:
            best = cat
            best_score = score
    return best


def cat_motion_on_bed(
    cats: list[Detection],
    bed: BBox,
    motion_blobs: list[MovingObject],
    min_cat_on_bed: float = 0.18,
    min_motion_overlap: float = 0.12,
) -> Detection | None:
    """Кот на кровати и его bbox пересекается с движущимся пятном."""
    from src.detection.on_couch import cat_on_couch

    for cat in cats:
        if not cat_on_couch(cat.bbox, bed, min_overlap=min_cat_on_bed):
            continue
        cat_a = max(1, bbox_area(cat.bbox))
        for blob in motion_blobs:
            inter = intersection_area(cat.bbox, blob.bbox)
            if inter / cat_a >= min_motion_overlap:
                return cat
            blob_a = max(1, blob.area)
            if inter / blob_a >= 0.25:
                return cat
    return None
