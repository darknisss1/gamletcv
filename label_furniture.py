#!/usr/bin/env python3
"""
Разметка YOLO: диван (со спинкой) + матрас.

  python label_furniture.py --images dataset/furniture/images/train

Клавиши:
  1 — рамка класса daybed (весь диван)
  2 — рамка класса mattress
  Enter — сохранить labels и следующий кадр
  s — пропустить кадр
  q — выход
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2

CLASS_IDS = {"daybed": 0, "mattress": 1}


def yolo_line(cls_id: int, box: tuple[int, int, int, int], w: int, h: int) -> str:
    x1, y1, x2, y2 = box
    cx = ((x1 + x2) / 2) / w
    cy = ((y1 + y2) / 2) / h
    bw = (x2 - x1) / w
    bh = (y2 - y1) / h
    return f"{cls_id} {cx:.6f} {cy:.6f} {bw:.6f} {bh:.6f}"


def pick_roi(frame, title: str) -> tuple[int, int, int, int] | None:
    roi = cv2.selectROI(title, frame, fromCenter=False, showCrosshair=True)
    x, y, rw, rh = (int(v) for v in roi)
    if rw <= 0 or rh <= 0:
        return None
    return x, y, x + rw, y + rh


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", default="dataset/furniture/images/train")
    parser.add_argument("--labels", default=None, help="по умолчанию ../labels/train")
    args = parser.parse_args()

    img_dir = Path(args.images)
    if not img_dir.is_dir():
        print("Нет папки:", img_dir)
        return 1

    if args.labels:
        label_dir = Path(args.labels)
    else:
        label_dir = img_dir.parent.parent / "labels" / img_dir.name
    label_dir.mkdir(parents=True, exist_ok=True)

    images = sorted(img_dir.glob("*.jpg")) + sorted(img_dir.glob("*.png"))
    if not images:
        print("Нет изображений в", img_dir)
        return 1

    print("Метки →", label_dir)
    for img_path in images:
        frame = cv2.imread(str(img_path))
        if frame is None:
            continue
        fh, fw = frame.shape[:2]
        lines: list[str] = []

        print("\n===", img_path.name, "===")
        bed = pick_roi(frame, "1=daybed: выделите весь диван со спинкой")
        if bed:
            lines.append(yolo_line(CLASS_IDS["daybed"], bed, fw, fh))

        matt = pick_roi(frame, "2=mattress: выделите матрас (Esc=пропустить)")
        if matt:
            lines.append(yolo_line(CLASS_IDS["mattress"], matt, fw, fh))

        if not lines:
            print("пропуск (нет рамок)")
            continue

        label_path = label_dir / (img_path.stem + ".txt")
        label_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("saved", label_path)

    cv2.destroyAllWindows()
    print("Готово. train: python train_furniture.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
