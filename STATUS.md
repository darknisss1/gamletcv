# Статус GamletCV

**Общий прогресс: 100%** — своя модель дивана подключена.

| Этап | Статус |
|------|--------|
| Датасет 24 кадра + авто-разметка | готово |
| Обучение CPU 35 эпох | готово, mAP50 **0.995** (val) |
| `config.yaml` → `furniture_yolo_model` | `runs/furniture/train/weights/best.pt` |
| Проверка RTSP | daybed **0.96**, bbox ≈ `(531,606)-(1609,1210)` |

## Запуск

```bash
python watch.py --config config.yaml
```

Диван: **своя YOLO** (раз в 2 с). Кот: **yolo11s** как раньше. `bed_zone.expand_bbox: false`.

## Проверка рамки

```bash
python scripts\check_bed_bbox.py --config config.yaml --out debug_bed_trained.jpg
```

## 2026-07-17

- Train ~8.5 мин на i7-9750H, CPU.
- Эталон daybed в датасете: ручная зона 520…1214 @ 2304×1296.
