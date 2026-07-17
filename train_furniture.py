#!/usr/bin/env python3
"""Дообучение YOLO на диван + матрас (CPU/GPU через Ultralytics)."""

from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/furniture.yaml")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--epochs", type=int, default=50)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=4, help="на CPU лучше 2–4")
    parser.add_argument(
        "--device",
        default="cpu",
        help="cpu | 0 (CUDA). По умолчанию cpu.",
    )
    parser.add_argument("--workers", type=int, default=0, help="0 стабильнее на Windows")
    args = parser.parse_args()

    data_path = ROOT / args.data
    if not data_path.is_file():
        example = ROOT / "data" / "furniture.example.yaml"
        print(f"Нет {data_path}. Скопируйте: copy {example} {data_path}")
        return 1

    if args.device == "cpu":
        print(
            "Режим CPU: batch=%s, epochs=%s — ориентир 20–60 мин на ~40 кадров."
            % (args.batch, args.epochs)
        )

    model = YOLO(args.model)
    model.train(
        data=str(data_path),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        workers=args.workers,
        project=str(ROOT / "runs" / "furniture"),
        name="train",
    )
    best = ROOT / "runs" / "furniture" / "train" / "weights" / "best.pt"
    print("Готово. В config.yaml:")
    print(f"  detection.furniture_yolo_model: {best.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
