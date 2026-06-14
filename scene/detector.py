import sys
import cv2
import torch
import numpy as np
from datetime import datetime
from pathlib import Path

sys.path.insert(0, '/usr/local/lib/python3.6/site-packages')
sys.path.insert(0, "/home/vision/projects/jetson-nano-people-analytics")
sys.path.insert(0, "/home/vision/projects/people-analytics")

from shared.config import *
from shared.database import log_person_count, log_dwell_start, log_dwell_end, log_tracking_event
from scene.centroidtracker import CentroidTracker
from models.common import DetectMultiBackend
from utils.general import non_max_suppression, scale_coords
from utils.torch_utils import select_device

def build_pipeline(sensor_id, width, height, fps):
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"framerate={fps}/1 ! "
        "nvvidconv flip-method=2 ! video/x-raw, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! "
        "appsink drop=true max-buffers=1"
    )

class SceneDetector:
    def __init__(self):
        print("[SceneDetector] Initializing...")

        # Load YOLOv5n
        self.device = select_device('0')
        self.model  = DetectMultiBackend(
            YOLO_WEIGHTS, device=self.device, fp16=True
        )
        self.model.warmup(imgsz=(1, 3, YOLO_IMG_SIZE, YOLO_IMG_SIZE))
        torch.cuda.empty_cache()

        # Tracker
        self.tracker = CentroidTracker(
            maxDisappeared=MAX_DISAPPEARED,
            maxDistance=MAX_DISTANCE
        )

        # Track active object IDs for dwell logging
        self.active_ids = set()

        # Track first-seen time per object ID for tracking_events / unique visitors
        self.first_seen = {}

        # Camera
        pipeline = build_pipeline(
            SCENE_CAMERA_ID, SCENE_WIDTH, SCENE_HEIGHT, SCENE_FPS
        )
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            raise RuntimeError("Failed to open scene camera!")

        print("[SceneDetector] Ready!")

    def process_frame(self, frame):
        # Preprocess
        img = cv2.resize(frame, (YOLO_IMG_SIZE, YOLO_IMG_SIZE))
        img = img[:, :, ::-1].transpose(2, 0, 1)
        img = np.ascontiguousarray(img)
        img = torch.from_numpy(img).to(self.device).half()
        img /= 255.0
        img = img.unsqueeze(0)

        # Inference
        with torch.no_grad():
            pred = self.model(img)
        pred = non_max_suppression(
            pred, YOLO_CONF, YOLO_IOU, classes=[0], max_det=50
        )

        rects = []
        if pred[0] is not None and len(pred[0]):
            det = pred[0]
            det[:, :4] = scale_coords(
                img.shape[2:], det[:, :4], frame.shape
            ).round()

            for *xyxy, conf, cls in det:
                x1, y1, x2, y2 = map(int, xyxy)
                w, h = x2 - x1, y2 - y1
                if w < MIN_PERSON_W or h < MIN_PERSON_H:
                    continue
                rects.append((x1, y1, x2, y2))
                if DEBUG_DRAW:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)

        # Update tracker
        objects = self.tracker.update(rects)

        # Track dwell events
        current_ids = set(objects.keys())
        now_ts = datetime.now()
        for oid in current_ids - self.active_ids:
            log_dwell_start(oid, camera_id=0)
            self.first_seen[oid] = now_ts
        for oid in self.active_ids - current_ids:
            log_dwell_end(oid, camera_id=0)
            started = self.first_seen.pop(oid, now_ts)
            log_tracking_event(oid, started.isoformat(), now_ts.isoformat(), camera_id=0)
        self.active_ids = current_ids

        # Person count
        count = len(rects)

        if DEBUG_DRAW:
            # Draw tracking info
            for (oid, centroid) in objects.items():
                cv2.putText(frame, f"ID {oid}",
                    (centroid[0]-10, centroid[1]-10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,255,0), 2)
                cv2.circle(frame, tuple(centroid), 4, (0,255,0), -1)

            cv2.putText(frame, f"People: {count}",
                (20, 50), cv2.FONT_HERSHEY_SIMPLEX,
                1, (0,255,0), 2, cv2.LINE_AA)

            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cv2.putText(frame, ts,
                (20, frame.shape[0]-20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

        return frame, count, objects

    def run(self):
        print("[SceneDetector] Starting detection loop...")
        last_log = datetime.now()

        while True:
            ret, frame = self.cap.read()
            if not ret:
                print("[SceneDetector] Frame read failed, retrying...")
                continue

            frame, count, objects = self.process_frame(frame)

            # Log count every 60 seconds
            now = datetime.now()
            if (now - last_log).seconds >= 60:
                log_person_count(count, camera_id=0)
                last_log = now

            if DEBUG_DRAW:
                cv2.imshow("Scene Camera", frame)
                if cv2.waitKey(1) & 0xFF == ord("q"):
                    break

        self.cap.release()
        if DEBUG_DRAW:
            cv2.destroyAllWindows()
        print("[SceneDetector] Stopped.")

if __name__ == "__main__":
    detector = SceneDetector()
    detector.run()
