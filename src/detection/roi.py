"""Crop ROI вокруг кровати для более точного YOLO по коту."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.detection.on_couch import BBox, Detection


@dataclass(frozen=True)
class BedRoi:
    x1: int
    y1: int
    x2: int
    y2: int

    @property
    def width(self) -> int:
        return max(0, self.x2 - self.x1)

    @property
    def height(self) -> int:
        return max(0, self.y2 - self.y1)

    def as_bbox(self) -> BBox:
        return (self.x1, self.y1, self.x2, self.y2)


def bed_roi_from_bbox(
    bed: BBox,
    frame_w: int,
    frame_h: int,
    padding: float = 0.08,
) -> BedRoi:
    """Вырезать зону кровати с небольшим полем вокруг."""
    x1, y1, x2, y2 = bed
    w, h = x2 - x1, y2 - y1
    pad_x = int(w * padding)
    pad_y = int(h * padding)
    return BedRoi(
        x1=max(0, x1 - pad_x),
        y1=max(0, y1 - pad_y),
        x2=min(frame_w, x2 + pad_x),
        y2=min(frame_h, y2 + pad_y),
    )


def crop_frame(frame: np.ndarray, roi: BedRoi) -> np.ndarray:
    if roi.width <= 0 or roi.height <= 0:
        return frame
    return frame[roi.y1 : roi.y2, roi.x1 : roi.x2].copy()


def shift_detections(detections: list[Detection], roi: BedRoi) -> list[Detection]:
    out: list[Detection] = []
    for det in detections:
        x1, y1, x2, y2 = det.bbox
        out.append(
            Detection(
                det.label,
                det.confidence,
                (x1 + roi.x1, y1 + roi.y1, x2 + roi.x1, y2 + roi.y1),
            )
        )
    return out


def is_frame_valid(frame: np.ndarray | None, min_mean: float = 8.0) -> bool:
    """Отбросить пустой/битый кадр после H.264 ошибок."""
    if frame is None or frame.size == 0:
        return False
    if frame.shape[0] < 32 or frame.shape[1] < 32:
        return False
    return float(frame.mean()) >= min_mean
