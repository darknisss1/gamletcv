"""Отдельная YOLO-модель дивана/матраса (дообучение на вашей комнате)."""

from __future__ import annotations

import cv2
import numpy as np
from ultralytics import YOLO

from src.detection.on_couch import Detection

# Имена классов в data/furniture.yaml → внутренние метки watch.py
LABEL_ALIASES: dict[str, str] = {
    "daybed": "bed",
    "bed_full": "bed",
    "sofa_bed": "bed",
    "couch": "couch",
    "bed": "bed",
    "mattress": "mattress",
}


class FurnitureYoloDetector:
    def __init__(self, model_path: str, inference_width: int = 960) -> None:
        self.model = YOLO(model_path)
        self.inference_width = inference_width
        names = self.model.names or {}
        self.class_names: dict[int, str] = {
            int(k): str(v) for k, v in names.items()
        }

    def detect(self, frame: np.ndarray, min_conf: float = 0.20) -> list[Detection]:
        h, w = frame.shape[:2]
        infer_w = self.inference_width if w > self.inference_width else w
        infer_h = max(32, int(h * infer_w / w))
        infer_h = ((infer_h + 31) // 32) * 32
        infer_w = ((infer_w + 31) // 32) * 32

        result = self.model.predict(
            frame,
            imgsz=(infer_h, infer_w),
            conf=min_conf,
            verbose=False,
        )[0]

        out: list[Detection] = []
        if result.boxes is None:
            return out

        for box in result.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            raw_name = self.class_names.get(cls_id, f"class_{cls_id}")
            label = LABEL_ALIASES.get(raw_name.lower(), raw_name.lower())
            x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
            out.append(Detection(label, conf, (x1, y1, x2, y2)))
        return out
