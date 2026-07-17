"""Геометрия: кот именно на диване, а не рядом."""

from __future__ import annotations

from dataclasses import dataclass

BBox = tuple[int, int, int, int]  # x1, y1, x2, y2


@dataclass
class Detection:
    label: str
    confidence: float
    bbox: BBox


def bbox_area(box: BBox) -> int:
    x1, y1, x2, y2 = box
    return max(0, x2 - x1) * max(0, y2 - y1)


def intersection_area(a: BBox, b: BBox) -> int:
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    return max(0, x2 - x1) * max(0, y2 - y1)


def overlap_ratio(cat: BBox, couch: BBox) -> float:
    cat_a = bbox_area(cat)
    if cat_a == 0:
        return 0.0
    return intersection_area(cat, couch) / cat_a


def foot_point(cat: BBox) -> tuple[int, int]:
    x1, _, x2, y2 = cat
    return (x1 + x2) // 2, y2


def point_in_bbox(point: tuple[int, int], box: BBox) -> bool:
    x, y = point
    x1, y1, x2, y2 = box
    return x1 <= x <= x2 and y1 <= y <= y2


def expand_bbox(box: BBox, margin: float = 0.0, frame_size: tuple[int, int] | None = None) -> BBox:
    """Расширить bbox — для пушистого кота контур YOLO часто меньше тела."""
    if margin <= 0:
        return box
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    x1 = int(x1 - w * margin)
    y1 = int(y1 - h * margin)
    x2 = int(x2 + w * margin)
    y2 = int(y2 + h * margin)
    if frame_size:
        fw, fh = frame_size
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(fw - 1, x2), min(fh - 1, y2)
    return (x1, y1, x2, y2)


def cat_on_couch(
    cat: BBox,
    couch: BBox,
    min_overlap: float = 0.25,
    fluffy_margin: float = 0.0,
    frame_size: tuple[int, int] | None = None,
) -> bool:
    """
    Кот на диване, если:
    - нижняя точка bbox кота внутри дивана (стоит/лежит на поверхности);
    - и хотя бы min_overlap площади кота пересекается с диваном.
    """
    cat_for_overlap = expand_bbox(cat, fluffy_margin, frame_size)
    ratio = overlap_ratio(cat_for_overlap, couch)
    if ratio < min_overlap:
        return False
    return point_in_bbox(foot_point(cat), couch)


def best_couch_for_cat(cat: BBox, couches: list[Detection]) -> Detection | None:
    if not couches:
        return None
    return max(couches, key=lambda c: overlap_ratio(cat, c.bbox))


def find_violations(
    cats: list[Detection],
    couches: list[Detection],
    min_overlap: float,
    fluffy_margin: float = 0.0,
    frame_size: tuple[int, int] | None = None,
) -> list[tuple[Detection, Detection]]:
    """Пары (кот, диван), где кот на диване."""
    pairs: list[tuple[Detection, Detection]] = []
    for cat in cats:
        couch = best_couch_for_cat(cat.bbox, couches)
        if couch and cat_on_couch(
            cat.bbox,
            couch.bbox,
            min_overlap,
            fluffy_margin=fluffy_margin,
            frame_size=frame_size,
        ):
            pairs.append((cat, couch))
    return pairs
