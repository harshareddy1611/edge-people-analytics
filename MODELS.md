# Model weights

The following files are excluded from git (see `.gitignore`) because
they're large binaries. Download them into the paths below before
running the system.

## Face / age / gender models (`face/models/`)

These are the well-known pretrained Caffe models for age and gender
classification (originally from the Levi & Hassner age/gender CNN, and
the OpenCV face detector). The `.prototxt` config files are included in
this repo; only the `.caffemodel` weight files need downloading:

- `face/models/face_net.caffemodel`   — OpenCV's SSD-based face detector
- `face/models/age_net.caffemodel`    — age classification
- `face/models/gender_net.caffemodel` — gender classification

These are commonly bundled together in age/gender estimation tutorials —
search for "OpenCV age gender deep learning caffemodel" to find a
mirrored copy if the original source is unavailable.

## YOLO weights (`scene/`)

The wide-angle person detector uses YOLOv5n weights:

```bash
# From the yolov5 repo root, or via the ultralytics package:
python3 -c "from ultralytics import YOLO; YOLO('yolov5n.pt')"
```

Update `YOLO_WEIGHTS` in `shared/config.py` to point at wherever the
downloaded `.pt` file ends up.

## Path configuration

This project currently hardcodes absolute paths (e.g.
`/home/vision/projects/people-analytics`) in several places, including
`shared/config.py` and the `sys.path.insert(...)` calls at the top of
each entry-point script. If you're deploying to a different path or
username, update these accordingly — see the open issue/TODO for making
these configurable via environment variables.
