# Агент: обучить диван и матрас

Цель: своя YOLO вместо COCO `bed`, чтобы рамка совпадала со **спинкой** и **матрасом** в вашей комнате.

## Роли

| Кто | Действие |
|-----|----------|
| **Вы** | 1 раз нарисовать рамки в `label_furniture.py` (или править в Roboflow) |
| **Агент (Cursor)** | сбор кадров, train, правка `config.yaml`, прогон `check_bed_bbox.py`, отчёт в `STATUS.md` |
| **watch.py** | кот — `yolo11s/n`, диван — `furniture_yolo_model` |

## Пайплайн

```bash
cd C:\github\gamletcv

# 1. Кадры с камеры (40 шт., раз в 3 с — разное освещение/кот опционально)
python scripts/collect_bed_frames.py --config config.yaml --count 40

# 2. Разметка: класс 0 daybed (весь диван), класс 1 mattress
python label_furniture.py --images dataset/furniture/images/train

# 3. 10–15% кадров в val (вручную перенести пары jpg+txt в images/val и labels/val)
copy data\furniture.example.yaml data\furniture.yaml

# 4. Обучение на CPU (по умолчанию)
python train_furniture.py --device cpu --epochs 50 --batch 4
# быстрее черновик: --epochs 30 --batch 2
# если есть NVIDIA: --device 0 --batch 8

# 5. Подключить в config.yaml (не коммитить секреты):
# detection.furniture_yolo_model: runs/furniture/train/weights/best.pt
# detection.bed_zone.expand_bbox: false   # рамка уже точная

python scripts/check_bed_bbox.py --config config.yaml
python watch.py --config config.yaml
```

## Сколько данных

| Объём | Ожидание |
|-------|----------|
| 20–30 кадров, аккуратная разметка | уже лучше COCO на вашем ракурсе |
| 50+ | стабильная рамка день/ночь |

## Промпт для агента

> Собери 40 кадров дивана, проверь что есть labels, запусти `train_furniture.py`, подключи `best.pt`, прогони `check_bed_bbox.py` и обнови STATUS.md.

## Классы

- `daybed` → в watch как `bed` (зона алерта, crop для кота)
- `mattress` → `mattress` (можно использовать для motion; приоритет зоны — `daybed` в `pick_main_furniture`)
