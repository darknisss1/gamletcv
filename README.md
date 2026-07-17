# Cat Couch Guard

Детектор «кот на диване» для IP-камеры **EKF Connect SCWF-USB**.

## Как подключаемся к EKF

Камера не отдаёт видео «напрямую в Python» — только по **RTSP**. Путь к потоку у каждой прошивки свой, поэтому цепочка такая:

```
EKF SCWF-USB  →  ONVIF (SOAP)  →  RTSP URL  →  OpenCV/FFmpeg  →  YOLO/VLM
```

### Шаг 1 — ONVIF (узнать URL)

Протокол **ONVIF** — стандарт для IP-камер. EKF Connect его поддерживает.

Скрипт `discover.py`:

1. **WS-Discovery** (UDP) — ищет камеры в Wi‑Fi без знания IP.
2. **GetProfiles** + **GetStreamUri** — камера сама возвращает правильный `rtsp://...`.
3. Перебирает типичные порты ONVIF: `80`, `8080`, `8899`, `8000`.

Логин/пароль — те же, что при настройке в приложении **EKF Connect Home**. В пароле не должно быть спецсимволов (ограничение EKF).

### Шаг 2 — RTSP (читать видео)

**OpenCV** + **FFmpeg** открывают поток:

- транспорт **TCP** (`rtsp_transport=tcp`) — стабильнее на Windows и Wi‑Fi;
- разрешение до **1080p**, H.264.

### Если ONVIF не сработал

1. [ONVIF Device Manager](https://sourceforge.net/projects/onvifdm/) → Live Video → скопировать RTSP URL.
2. В `config.yaml` поле `camera.rtsp_url` или:
   ```bash
   python discover.py --rtsp-url "rtsp://..." --password ПАРОЛЬ
   ```

### Сеть

- ПК и камера в одной **2.4 ГГц** Wi‑Fi сети.
- IP камеры — в приложении EKF Connect (настройки устройства).

## Режимы запуска

| Скрипт | Режим |
|--------|--------|
| `python watch.py` | **Движение кота** на статичной кровати (motion + YOLO cat) |
| `python watch_yolo.py` | Только YOLO: кот + кровать, без motion (откат) |
| `python record_dataset.py` | Сбор кадров для дообучения (`s` кот, `n` без кота) |

```bash
python watch_yolo.py --config config.yolo.yaml
python record_dataset.py --out dataset/images
```

### Точность кота

- `detection.cat_roi_enabled: true` — YOLO только по crop зоны кровати (рекомендуется).
- `detection.inference_width: 1280` + `enhance_contrast: true` — для белого пушистого кота.
- Соберите 300+ кадров (`record_dataset.py`), разметьте в Roboflow/CVAT, fine-tune `yolo11s.pt`.

```bash
cd gamletcv
pip install -r requirements.txt
copy config.example.yaml config.yaml
python calibrate_bed.py
python watch.py
```

## Рекомендации для EKF SCWF-USB

- Выключите **авто-слежение** — иначе камера поворачивается за котом и диван уезжает из кадра.
- Зафиксируйте угол на диван (весь диван в кадре).
