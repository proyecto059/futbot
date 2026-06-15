# Calibración HSV con YOLO como Ground Truth

**Fecha:** 11 Abril 2026
**Objetivo:** Eliminar falsos positivos del detector HSV usando el modelo YOLO ONNX como referencia para calibrar los umbrales de color.

---

## Problema

El detector HSV (`AdaptiveOrangeBallDetector`) no detectaba la pelota naranja en la Raspberry Pi. El diagnóstico anterior mostraba:

- Detección inestable con falsos positivos de la mesa de madera pulida
- Parámetros HSV calibrados a ojo que no coincidían con la realidad
- El adaptivo subía automáticamente los umbrales de S y V, excluyendo la pelota real

## Solución: YOLO como ground truth

Se usó el modelo YOLO ONNX int8 (entrenado para detectar pelota y robot) ya existente en el repositorio (`model.onnx`, 20MB) para:

1. Encontrar la pelota en el frame (barrido de servos + YOLO)
2. Extraer los valores HSV reales dentro de la bounding box de YOLO
3. Comparar con lo que el detector HSV encontraba
4. Ajustar los umbrales HSV basándose en datos reales

### Modelo YOLO

- **Input:** `[1, 3, 320, 320]` float32 (BGR→RGB, normalizado 0-1)
- **Output:** `[1, 300, 6]` — NMS incluido, cada fila: `[x1, y1, x2, y2, conf, class_id]`
- **Clase 0:** pelota, **Clase 1:** robot
- **FPS en RPi:** ~1.7 (demasiado lento para control de servos, pero suficiente para diagnóstico)

### Hallazgos con YOLO

El script `diag_yolo_hsv.py` barría el pan de 40° a 150° buscando la pelota con YOLO, y una vez encontrada medía los píxeles HSV dentro de la bounding box:

| Métrica | Hue | Saturation | Value |
|---------|-----|------------|-------|
| Media   | ~20 | 251        | ~40   |
| Mediana | 0   | 255        | ~35   |
| P10     | 0   | 255        | 11    |
| P90     | 170 | 255        | ~80   |

**Hallazgos clave:**

- **Hue = 0**: La pelota tiene H=0 (rojo puro), no H=5-20 como se asumía. Además tiene píxeles en H≈170-178 (rojo wrap-around del espacio HSV).
- **Saturación = 255**: Casi todos los píxeles tienen saturación máxima.
- **Value muy bajo**: Mediana V≈33, con P10=11. El umbral anterior V≥45 excluía la mayoría de la pelota.
- **Radio grande**: La pelota aparece con radius≈85 píxeles, excediendo el filtro ADAPTIVE_MAX_RADIUS=40.
- **Circularidad baja**: circ≈0.28 por iluminación desigual, bajo el filtro ADAPTIVE_MIN_CIRCULARITY=0.35.

### Filtros que rechazaban la pelota

Se encontró que el detector HSV rechazaba la pelota por **tres motivos simultáneos**:

1. `ADAPTIVE_MAX_RADIUS=40` — la pelota tiene radius≈85
2. `ADAPTIVE_MIN_CIRCULARITY=0.35` — la pelota tiene circ≈0.28
3. El adaptivo subía `val_min` a 35+ cuando `v_median < 50`, pero la pelota tiene V≈33

## Cambios realizados

### `hardware.py`

| Parámetro | Antes | Después | Razón |
|-----------|-------|---------|-------|
| `CAMERA_EXPOSURE` | 500 | 800 | Pelota casi invisible con exposure bajo |
| `HSV_LO` | `(5, 160, 45)` | `(0, 230, 20)` | YOLO: H=0, S=255, V≈33 |
| `HSV_HI` | `(20, 255, 255)` | `(10, 255, 255)` | Pelota tiene H≈0 |
| `HSV_LO2` | — | `(168, 230, 20)` | Rojo wrap-around (H≈170) |
| `HSV_HI2` | — | `(179, 255, 255)` | Rojo wrap-around |
| `ADAPTIVE_MIN_CIRCULARITY` | 0.35 | 0.20 | Pelota circ≈0.28 con luz desigual |
| `ADAPTIVE_MAX_RADIUS` | 40 | 150 | Pelota grande (radius≈85) |
| `ADAPTIVE_ORANGE_HUE_MIN` | 5 | 0 | H=0 es válido |
| `ADAPTIVE_ORANGE_HUE_MAX` | 30 | 15 | Limitar falsos positivos |

Se añadió soporte para **rango HSV dual** (H=0-10 y H=168-179) en `_build_hue_mask()` para manejar el wrap-around del rojo.

Se simplificó `_update_adaptive_thresholds()` para usar umbrales fijos (S≥220, V≥15 en strict; S≥200, V≥10 en relaxed) en lugar de la lógica adaptiva basada en V-median que subía demasiado los umbrales.

### `test_servos.py`

Se simplificó `run_test_servos()` a una sola implementación con EMA proporcional. Se eliminaron las dos copias duplicadas del loop de tracking (los bloques de confirmación y jump-filter que ya no se usaban).

### Dependencias (`pyproject.toml`)

Se añadió `onnxruntime` como dependencia para poder ejecutar el modelo YOLO.

### Scripts nuevos

- **`diag_yolo_hsv.py`** — Diagnóstico que usa YOLO como ground truth para:
  1. Barrer servos buscando la pelota con YOLO
  2. Medir valores HSV reales dentro de la bounding box
  3. Comparar detecciones HSV vs YOLO (verdaderos positivos, falsos positivos)
  4. Sugerir umbrales HSV basados en percentiles

- **`YOLOBallDetector`** en `hardware.py` — Detector basado en YOLO ONNX (disponible para uso futuro, pero no se usa en tracking por FPS limitado)

## Resultados

| Métrica | Antes (HSV original) | Después (HSV calibrado con YOLO) |
|---------|---------------------|----------------------------------|
| FPS | 11.5 (exp=500) / 7.1 (exp=800) | 7.1 (exp=800) |
| Detección | 0% (la pelota nunca se detectaba) | **94%** |
| Falsos positivos | N/A (no detectaba nada) | ~1-2% (ocasionales) |
| Tracking estable | No | Sí (pan≈71, cx≈300-320) |

## YOLO como detector principal (no usado)

Se implementó `YOLOBallDetector` completo pero se descartó para tracking en tiempo real:

- **Ventaja:** 0 falsos positivos, detección semántica real
- **Desventaja:** 1.7 FPS en Raspberry Pi (imposible para servo tracking)
- **Uso actual:** Solo como herramienta de diagnóstico/calibración

## Lecciones aprendidas

1. **No calibrar HSV a ojo** — Los valores HSV de una pelota naranja en baja luz son muy diferentes a lo esperado (H=0, no H=10-15).
2. **El rojo wrap-around** — El rojo en HSV aparece en ambos extremos (H≈0 y H≈170), necesitando dos rangos de máscara.
3. **Verificar cada filtro** — La pelota era rechazada por tres filtros simultáneamente (radio, circularidad, V_min). Sin diagnóstico paso a paso no se habría encontrado.
4. **El adaptivo puede ser contraproducente** — La lógica adaptiva subía V_min a 35+ cuando la imagen era oscura, excluyendo la pelota que tenía V≈33.
