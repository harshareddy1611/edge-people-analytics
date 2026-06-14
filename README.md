# People Analytics (Jetson Nano)

A real-time people-counting and demographic analytics system built for
the Jetson Nano (4GB), using two CSI cameras:

- **Wide-angle camera** — person detection and tracking (YOLOv5n), foot
  traffic counts, dwell time, unique visitors.
- **Narrow-angle camera** — age/gender estimation, attention detection
  (eye-cascade based), per-person dwell and "attentive time" tracking.

Results are stored in SQLite and visualized in a local web dashboard
with day/week/month historical views, an hourly activity heatmap, and
demographic breakdowns. An optional fullscreen ad-viewer can display
category-targeted content (e.g. gym/beauty/finance ads) based on the
detected demographic mix.

## Project layout

```
scene/      — wide-angle camera: YOLOv5n person detection + tracking
face/       — narrow-angle camera: face detection, age/gender, attention
shared/     — config, SQLite schema and query helpers
dashboard/  — Flask web dashboard (historical analytics)
adviewer/   — Flask fullscreen ad slideshow viewer
calibration/— camera calibration utilities
```

## Requirements

- Jetson Nano (4GB) with JetPack, two CSI cameras (e.g. IMX219)
- Python 3.6 (matches the JetPack-provided OpenCV/CUDA builds)
- OpenCV with CUDA DNN support, PyTorch (for YOLOv5n), Flask, scipy

## Setup

1. Clone this repo to `~/projects/people-analytics` (or update the
   hardcoded paths in `shared/config.py` and the `sys.path.insert(...)`
   calls at the top of each entry-point script if using a different
   path).
2. Download the model weights — see [MODELS.md](MODELS.md).
3. Run calibration if needed (`calibration/calibrate.py`).
4. Start everything:
   ```bash
   ./run_all.sh
   ```
   This launches the scene detector, face analytics, dashboard
   (`:5000`), and ad viewer (`:5001`).

## Configuration

All tunable settings (camera IDs, resolutions, detection thresholds,
tracker tolerances, ad categories, etc.) live in `shared/config.py`.

Notable settings:
- `DEBUG_DRAW` — set to `True` to show live camera preview windows with
  bounding boxes/labels (requires a display). Defaults to `False` for
  headless operation.
- `AD_WINDOW_SECS` / `AD_POLL_SECS` — control how quickly the ad viewer
  responds to demographic changes.
- `FACE_MAX_DISAPPEARED` / `FACE_MAX_DISTANCE` — tracker tolerance for
  the face camera; affects dwell-time stability.

## Data

All events (person counts, tracking sessions, face/demographic samples,
dwell times, ad selections) are stored in a SQLite database at
`data/analytics.db`. The dashboard queries this directly — no separate
database server needed.

## Ad viewer content

Drop images into `adviewer/ads/<category>/` (one folder per category,
matching `AD_CATEGORIES` in `shared/config.py`, plus `default/` as a
fallback). See `adviewer/ads/README.md`.

## License

(Add a license — see the section on open source below before publishing.)
