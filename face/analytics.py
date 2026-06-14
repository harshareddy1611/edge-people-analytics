import sys
import os
sys.path.insert(0, '/usr/local/lib/python3.6/site-packages')
sys.path.insert(0, '/home/vision/projects/people-analytics')

import cv2
import numpy as np
from datetime import datetime
from collections import defaultdict, deque
from shared.config import *
from shared.database import log_face_event, log_dwell_start, log_dwell_end, log_ad_selection
from face.face_tracker import FaceTracker

MODELS_DIR   = "/home/vision/projects/people-analytics/face/models"
FACE_PROTO   = f"{MODELS_DIR}/face_deploy.prototxt"
FACE_MODEL   = f"{MODELS_DIR}/face_net.caffemodel"
AGE_PROTO    = f"{MODELS_DIR}/age_deploy.prototxt"
AGE_MODEL    = f"{MODELS_DIR}/age_net.caffemodel"
GENDER_PROTO = f"{MODELS_DIR}/gender_deploy.prototxt"
GENDER_MODEL = f"{MODELS_DIR}/gender_net.caffemodel"

AGE_LIST    = ['0-2','4-6','8-12','15-20','25-32','38-43','48-53','60-100']
GENDER_LIST = ['Male', 'Female']
MEAN_VALUES = (78.4263377603, 87.7689143744, 114.895847746)
AGE_MAP     = {
    '0-2':'0-17','4-6':'0-17','8-12':'0-17','15-20':'0-17',
    '25-32':'18-28','38-43':'29-45','48-53':'46+','60-100':'46+',
}

# Face tracker tuning — controls how dwell time / smoothing identity
# is maintained across frames for the face/demographics camera.
#
# maxDisappeared: how many consecutive missed frames before a face is
#   considered "gone" (ends dwell). At FACE_FPS=8, 40 frames ≈ ~5 sec
#   tolerance — the face detector can be noisy frame-to-frame (lighting,
#   head angle), and a too-short tolerance causes the same person to be
#   re-registered as a "new" object repeatedly, fragmenting dwell time
#   and inflating unique-visitor counts.
# maxDistance: max centroid movement (px) between frames to still be
#   considered the same face. FACE_WIDTH/HEIGHT = 640x480. Increased
#   from 120 to 180 since a multi-second dropout (above) means the face
#   may have moved further by the time it's redetected.
FACE_MAX_DISAPPEARED = 40
FACE_MAX_DISTANCE    = 180

# Smoothing buffer size
SMOOTH_BUFFER = 10

def build_pipeline(sensor_id, width, height, fps):
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} "
        f"wbmode=1 aelock=true ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"framerate={fps}/1 ! "
        "nvvidconv flip-method=2 ! video/x-raw, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! "
        "appsink drop=true max-buffers=1"
    )

class FaceAnalytics:
    @staticmethod
    def _find_cascade_file(filename):
        """
        Locate a Haar cascade XML file across common OpenCV install
        locations. Falls back gracefully (returns None) if not found —
        callers should handle that by disabling the dependent feature.
        """
        candidates = []

        # cv2.data, when available
        try:
            candidates.append(os.path.join(cv2.data.haarcascades, filename))
        except AttributeError:
            pass

        # Common system/package install paths across OpenCV versions
        candidates += [
            f"/usr/share/opencv4/haarcascades/{filename}",
            f"/usr/share/opencv/haarcascades/{filename}",
            f"/usr/local/share/opencv4/haarcascades/{filename}",
            f"/usr/local/share/opencv/haarcascades/{filename}",
        ]

        # Search inside the installed cv2 package directory itself
        try:
            cv2_dir = os.path.dirname(cv2.__file__)
            candidates.append(os.path.join(cv2_dir, "data", filename))
        except Exception:
            pass

        for path in candidates:
            if os.path.isfile(path):
                return path

        return None

    def __init__(self):
        print("[FaceAnalytics] Loading models...")

        self.face_net   = cv2.dnn.readNet(FACE_MODEL,   FACE_PROTO)
        self.age_net    = cv2.dnn.readNet(AGE_MODEL,    AGE_PROTO)
        self.gender_net = cv2.dnn.readNet(GENDER_MODEL, GENDER_PROTO)

        self.face_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.face_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        self.age_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.age_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)
        self.gender_net.setPreferableBackend(cv2.dnn.DNN_BACKEND_CUDA)
        self.gender_net.setPreferableTarget(cv2.dnn.DNN_TARGET_CUDA)

        # Eye cascade — used as a lightweight "attention" signal.
        # If both eyes are visible in the face crop, the person is
        # roughly facing the camera. Runs on CPU; Haar cascades are
        # cheap enough not to need CUDA.
        #
        # cv2.data isn't available on all OpenCV builds (notably some
        # Jetson/JetPack builds), so search common install locations
        # for the cascade XML instead of relying on it.
        eye_cascade_path = self._find_cascade_file("haarcascade_eye.xml")
        if eye_cascade_path:
            self.eye_cascade = cv2.CascadeClassifier(eye_cascade_path)
            if self.eye_cascade.empty():
                print(f"[FaceAnalytics] WARNING: failed to load eye cascade "
                      f"from {eye_cascade_path} — attention detection disabled.")
                self.eye_cascade = None
            else:
                print(f"[FaceAnalytics] Loaded eye cascade from {eye_cascade_path}")
        else:
            print("[FaceAnalytics] WARNING: haarcascade_eye.xml not found "
                  "— attention detection disabled.")
            self.eye_cascade = None

        pipeline = build_pipeline(
            FACE_CAMERA_ID, FACE_WIDTH, FACE_HEIGHT, FACE_FPS
        )
        self.cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
        if not self.cap.isOpened():
            raise RuntimeError("Failed to open face camera!")

        # Stable face tracker — gives each face a persistent object_id
        # across frames so dwell time and smoothing aren't reset by
        # small head movements (previous grid-cell approach was too jumpy).
        self.tracker = FaceTracker(
            maxDisappeared=FACE_MAX_DISAPPEARED,
            maxDistance=FACE_MAX_DISTANCE
        )

        # Smoothing buffers per tracked face (object_id)
        self.age_buffers      = defaultdict(lambda: deque(maxlen=SMOOTH_BUFFER))
        self.gender_buffers   = defaultdict(lambda: deque(maxlen=SMOOTH_BUFFER))
        self.attention_buffers = defaultdict(lambda: deque(maxlen=SMOOTH_BUFFER))

        # Track last logged (gender, age_group) and time per object_id,
        # so we only write to DB when the smoothed prediction changes
        # or after FACE_LOG_INTERVAL seconds — avoids logging every frame.
        self.last_logged = {}  # object_id -> (gender, age_group, last_log_time)

        # Dwell tracking — keyed by tracked object_id. Dwell starts as soon
        # as a face is detected and tracked continuously (no frontal gate —
        # the bbox aspect-ratio heuristic was too noisy to gate dwell on).
        self.dwell_start = {}  # object_id -> start_time

        # Accumulated "attentive" time per tracked face — only increments
        # on frames where is_attentive=True, using the wall-clock delta
        # since that face's last processed frame. This gives a running
        # total of actual attentive seconds, independent of how long the
        # person has simply been present (dwell) or how long they spent
        # looking away.
        self.attentive_seconds = {}  # object_id -> accumulated seconds
        self.last_frame_time    = {}  # object_id -> datetime of last frame processed

        # Ad selection
        self.recent_demographics = []
        self.last_ad_update      = datetime.now()
        self.current_ad          = "default"

        print("[FaceAnalytics] Ready!")

    def detect_faces(self, frame):
        h, w = frame.shape[:2]
        blob = cv2.dnn.blobFromImage(
            frame, 1.0, (300,300), [104,117,123], True, False
        )
        self.face_net.setInput(blob)
        dets  = self.face_net.forward()
        faces = []
        for i in range(dets.shape[2]):
            conf = float(dets[0,0,i,2])
            if conf > 0.5:
                x1 = max(0, int(dets[0,0,i,3]*w) - 20)
                y1 = max(0, int(dets[0,0,i,4]*h) - 20)
                x2 = min(w, int(dets[0,0,i,5]*w) + 20)
                y2 = min(h, int(dets[0,0,i,6]*h) + 20)
                faces.append((x1, y1, x2, y2, conf))
        return faces

    def predict_age_gender(self, face_crop):
        blob = cv2.dnn.blobFromImage(
            face_crop, 1.0, (227,227), MEAN_VALUES, swapRB=False
        )
        self.gender_net.setInput(blob)
        gp     = self.gender_net.forward()
        gender = GENDER_LIST[gp[0].argmax()]
        g_conf = float(gp[0].max())

        self.age_net.setInput(blob)
        ap  = self.age_net.forward()
        age = AGE_LIST[ap[0].argmax()]

        return gender, round(g_conf, 2), age

    def check_attentive(self, face_crop):
        """
        Returns True if at least 2 eyes are detected in the face crop —
        a simple proxy for "facing the camera". A profile/turned face
        typically only shows 0-1 eyes to a frontal eye detector.
        """
        if self.eye_cascade is None or face_crop.size == 0:
            return False

        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        eyes = self.eye_cascade.detectMultiScale(
            gray, scaleFactor=1.1, minNeighbors=5, minSize=(15, 15)
        )
        return len(eyes) >= 2

    def smooth_prediction(self, key, gender, age):
        """Return majority vote from recent predictions."""
        self.gender_buffers[key].append(gender)
        self.age_buffers[key].append(age)

        # Majority gender
        g_counts  = defaultdict(int)
        for g in self.gender_buffers[key]:
            g_counts[g] += 1
        smooth_gender = max(g_counts, key=g_counts.get)

        # Majority age
        a_counts  = defaultdict(int)
        for a in self.age_buffers[key]:
            a_counts[a] += 1
        smooth_age = max(a_counts, key=a_counts.get)

        return smooth_gender, smooth_age

    def update_dwell(self, object_id, now):
        """
        Track dwell time as continuous presence of a tracked face.
        Starts as soon as the face is first tracked; ends when the
        tracker loses it (handled in process_frame's cleanup step).
        Returns current dwell duration in seconds.
        """
        if object_id not in self.dwell_start:
            self.dwell_start[object_id] = now
            log_dwell_start(object_id, camera_id=FACE_CAMERA_ID)

        return (now - self.dwell_start[object_id]).total_seconds()

    def update_ad(self, person_count):
        now     = datetime.now()
        elapsed = (now - self.last_ad_update).total_seconds()
        if elapsed < AD_WINDOW_SECS or not self.recent_demographics:
            return self.current_ad

        counts = defaultdict(int)
        for gender, age_group in self.recent_demographics:
            counts[(age_group, gender)] += 1

        dominant        = max(counts, key=counts.get)
        age_key, gender_key = dominant
        new_ad          = AD_CATEGORIES.get((age_key, gender_key), "default")

        if new_ad != self.current_ad:
            print(f"[AdSelector] {self.current_ad} → {new_ad} "
                  f"({gender_key}, {age_key})")
            log_ad_selection(new_ad, age_key, gender_key, person_count)
            self.current_ad = new_ad

        self.recent_demographics = []
        self.last_ad_update      = now
        return self.current_ad

    def process_frame(self, frame):
        now   = datetime.now()
        faces = self.detect_faces(frame)

        # Update tracker — gives each face a stable object_id across frames
        rects = [(x1, y1, x2, y2) for (x1, y1, x2, y2, conf) in faces]
        # Keep a lookup from rect -> conf so we can retrieve it after tracking
        conf_by_rect = {(x1,y1,x2,y2): conf for (x1,y1,x2,y2,conf) in faces}
        tracked = self.tracker.update(rects)

        current_ids = set(tracked.keys())

        for object_id, (centroid, (x1, y1, x2, y2)) in tracked.items():
            face_crop = frame[y1:y2, x1:x2]
            if face_crop.size == 0:
                continue

            g_conf = conf_by_rect.get((x1,y1,x2,y2), 0.0)

            # Predict
            gender, _, age_raw = self.predict_age_gender(face_crop)
            age_group = AGE_MAP.get(age_raw, '18-28')

            # Smooth predictions per tracked face
            smooth_gender, smooth_age = self.smooth_prediction(
                object_id, gender, age_group
            )

            # Attention signal — eye-detection based, buffered per face
            # so the logged value reflects recent frames, not just one.
            attentive_now = self.check_attentive(face_crop)
            self.attention_buffers[object_id].append(1 if attentive_now else 0)
            buf = self.attention_buffers[object_id]
            attention_ratio = sum(buf) / len(buf)
            is_attentive = attention_ratio >= 0.5

            # Accumulate attentive time: add the wall-clock gap since this
            # face's last processed frame, but only if currently attentive.
            # This way, looking away pauses the counter (doesn't reset it),
            # and it resumes accumulating once attention returns.
            last_t = self.last_frame_time.get(object_id, now)
            frame_dt = (now - last_t).total_seconds()
            if is_attentive:
                self.attentive_seconds[object_id] = (
                    self.attentive_seconds.get(object_id, 0.0) + frame_dt
                )
            self.last_frame_time[object_id] = now

            # Dwell time — continuous presence of this tracked face
            dwell_secs = self.update_dwell(object_id, now)

            # Log to DB only when the smoothed prediction changes for this
            # face, or FACE_LOG_INTERVAL seconds have passed since last log.
            prev = self.last_logged.get(object_id)
            should_log = (
                prev is None
                or prev[0] != smooth_gender
                or prev[1] != smooth_age
                or (now - prev[2]).total_seconds() >= FACE_LOG_INTERVAL
            )
            if should_log:
                log_face_event(
                    object_id, smooth_gender, smooth_age,
                    g_conf, camera_id=FACE_CAMERA_ID,
                    is_attentive=is_attentive
                )
                self.last_logged[object_id] = (smooth_gender, smooth_age, now)

            # Add to ad window — use all tracked faces, not just "frontal"
            # ones, since frontal-ness here isn't reliable
            self.recent_demographics.append((smooth_gender, smooth_age))

            if DEBUG_DRAW:
                # Draw box — color reflects attention (eye-detection based),
                # not the old aspect-ratio "frontal" heuristic.
                color = (0,255,0) if is_attentive else (0,165,255)
                cv2.rectangle(frame, (x1,y1), (x2,y2), color, 2)

                # Label
                attn_secs = self.attentive_seconds.get(object_id, 0.0)
                attn   = "ATTENTIVE" if is_attentive else "looking away"
                label  = f"ID{object_id} {smooth_gender} {smooth_age}"
                dwell  = f"Dwell {dwell_secs:.1f}s / Attn {attn_secs:.1f}s"
                cv2.putText(frame, label,
                    (max(0,x1), max(20,y1-25)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
                cv2.putText(frame, f"{attn} {dwell}",
                    (max(0,x1), max(20,y1-5)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

        # End dwell + clean up smoothing/log state for faces that left frame
        gone = set(self.dwell_start.keys()) - current_ids
        for object_id in gone:
            duration = (now - self.dwell_start[object_id]).total_seconds()
            if duration >= DWELL_MIN_SECS:
                attentive_secs = self.attentive_seconds.get(object_id, 0.0)
                log_dwell_end(
                    object_id, camera_id=FACE_CAMERA_ID,
                    attentive_duration=attentive_secs
                )
            del self.dwell_start[object_id]
            self.age_buffers.pop(object_id, None)
            self.gender_buffers.pop(object_id, None)
            self.attention_buffers.pop(object_id, None)
            self.attentive_seconds.pop(object_id, None)
            self.last_frame_time.pop(object_id, None)
            self.last_logged.pop(object_id, None)

        # Update ad
        current_ad = self.update_ad(len(faces))

        if DEBUG_DRAW:
            # Overlay
            cv2.putText(frame, f"Faces: {len(faces)}",
                (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
            cv2.putText(frame, f"Ad: {current_ad}",
                (20, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,255), 2)
            cv2.putText(frame, now.strftime("%Y-%m-%d %H:%M:%S"),
                (20, frame.shape[0]-20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255,255,255), 1)

        return frame, len(faces)

    def run(self):
        print("[FaceAnalytics] Starting...")
        while True:
            ret, frame = self.cap.read()
            if not ret:
                continue
            frame, _ = self.process_frame(frame)
            if DEBUG_DRAW:
                cv2.imshow("Face Camera", frame)
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    break
        self.cap.release()
        if DEBUG_DRAW:
            cv2.destroyAllWindows()

if __name__ == "__main__":
    analytics = FaceAnalytics()
    analytics.run()
