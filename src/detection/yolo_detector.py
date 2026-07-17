"""YOLO: кот + мебель. По умолчанию одна модель (быстро). World — опционально."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from ultralytics import YOLO

from src.detection.on_couch import BBox, Detection
from src.detection.roi import bed_roi_from_bbox, crop_frame, shift_detections

CAT_CLASS = 15
PERSON_CLASS = 0
FURNITURE_CLASSES: dict[int, str] = {
    57: "couch",
    59: "bed",
    56: "chair",
}
DEFAULT_FURNITURE_NAMES = ["couch", "bed", "chair", "mattress"]


@dataclass
class FrameDetections:
    cats: list[Detection]
    couches: list[Detection]
    persons: list[Detection]
    inference_ms: float


def enhance_contrast(frame: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
    l_channel, a_channel, b_channel = cv2.split(lab)
    clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
    l_channel = clahe.apply(l_channel)
    merged = cv2.merge([l_channel, a_channel, b_channel])
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


class YoloDetector:
    def __init__(
        self,
        model_path: str,
        inference_width: int = 960,
        furniture_class_ids: set[int] | None = None,
        furniture_names: list[str] | None = None,
        world_model: str = "yolov8s-worldv2.pt",
        use_world_model: bool = False,
        enhance: bool = False,
    ) -> None:
        self.model = YOLO(model_path)
        self.inference_width = inference_width
        self.furniture_class_ids = furniture_class_ids or set(FURNITURE_CLASSES)
        self.furniture_names = furniture_names or DEFAULT_FURNITURE_NAMES
        self.enhance = enhance
        self.use_world_model = use_world_model

        self.furniture_model = None
        if use_world_model:
            self.furniture_model = YOLO(world_model)
            self.furniture_model.set_classes(self.furniture_names)

    def detect(
        self,
        frame: np.ndarray,
        cat_conf: float,
        couch_conf: float,
        bed_conf: float | None = None,
    ) -> FrameDetections:
        bed_conf = couch_conf if bed_conf is None else bed_conf
        h, w = frame.shape[:2]
        infer_w = self.inference_width if w > self.inference_width else w
        infer_h = max(32, int(h * infer_w / w))
        infer_h = ((infer_h + 31) // 32) * 32
        infer_w = ((infer_w + 31) // 32) * 32
        src = enhance_contrast(frame) if self.enhance else frame
        min_conf = min(cat_conf, couch_conf, bed_conf, 0.06)

        result = self.model.predict(
            src,
            imgsz=(infer_h, infer_w),
            conf=min_conf,
            verbose=False,
        )[0]

        cats: list[Detection] = []
        couches: list[Detection] = []
        persons: list[Detection] = []

        if result.boxes is not None:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                bbox = (x1, y1, x2, y2)

                if cls_id == CAT_CLASS and conf >= cat_conf:
                    cats.append(Detection("cat", conf, bbox))
                elif cls_id == PERSON_CLASS and conf >= 0.35:
                    persons.append(Detection("person", conf, bbox))
                elif cls_id == 59 and conf >= bed_conf:
                    couches.append(Detection("bed", conf, bbox))
                elif cls_id in self.furniture_class_ids and conf >= couch_conf:
                    label = FURNITURE_CLASSES.get(cls_id, "furniture")
                    if label == "bed":
                        continue
                    couches.append(Detection(label, conf, bbox))

        infer_ms = float((result.speed or {}).get("inference", 0.0))

        if self.furniture_model is not None:
            furn_result = self.furniture_model.predict(
                src,
                imgsz=(infer_h, infer_w),
                conf=min_conf,
                verbose=False,
            )[0]
            names = furn_result.names or {}
            if furn_result.boxes is not None:
                for box in furn_result.boxes:
                    cls_id = int(box.cls[0])
                    conf = float(box.conf[0])
                    if conf < couch_conf:
                        continue
                    label = names.get(
                        cls_id,
                        self.furniture_names[cls_id] if cls_id < len(self.furniture_names) else "furniture",
                    )
                    if label not in self.furniture_names:
                        continue
                    x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
                    couches.append(Detection(label, conf, (x1, y1, x2, y2)))
            infer_ms += float((furn_result.speed or {}).get("inference", 0.0))

        return FrameDetections(cats=cats, couches=couches, persons=persons, inference_ms=infer_ms)

    def detect_cats_in_bed(
        self,
        frame: np.ndarray,
        bed: BBox,
        cat_conf: float,
        roi_padding: float = 0.08,
    ) -> tuple[list[Detection], float]:
        """YOLO только по crop зоны кровати — кот крупнее, меньше ложных срабатываний."""
        h, w = frame.shape[:2]
        roi = bed_roi_from_bbox(bed, w, h, roi_padding)
        crop = crop_frame(frame, roi)
        if crop.size == 0:
            return [], 0.0
        dets = self.detect(crop, cat_conf=cat_conf, couch_conf=0.99, bed_conf=0.99)
        return shift_detections(dets.cats, roi), dets.inference_ms
