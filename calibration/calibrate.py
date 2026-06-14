import sys
import cv2
import numpy as np
import os

sys.path.insert(0, '/usr/local/lib/python3.6/site-packages')
sys.path.insert(0, '/home/vision/projects/people-analytics')

from shared.config import SCENE_CAMERA_ID, SCENE_WIDTH, SCENE_HEIGHT

# Checkerboard settings — count INNER corners
# e.g. a 9x6 board has 8x5 inner corners
CHECKERBOARD = (8, 5)  # change this to match YOUR board inner corners
SQUARE_SIZE  = 25      # size of each square in mm — measure yours!

SAVE_PATH = "/home/vision/projects/people-analytics/calibration/camera_matrix.npz"
IMAGES_DIR = "/home/vision/projects/people-analytics/calibration/images"

def build_pipeline(sensor_id, width, height):
    return (
        f"nvarguscamerasrc sensor-id={sensor_id} ! "
        f"video/x-raw(memory:NVMM), width={width}, height={height}, "
        f"framerate=30/1 ! "
        "nvvidconv flip-method=2 ! video/x-raw, format=BGRx ! "
        "videoconvert ! video/x-raw, format=BGR ! "
        "appsink drop=true max-buffers=1"
    )

def calibrate():
    os.makedirs(IMAGES_DIR, exist_ok=True)

    objp = np.zeros((CHECKERBOARD[0]*CHECKERBOARD[1], 3), np.float32)
    objp[:, :2] = np.mgrid[0:CHECKERBOARD[0],
                            0:CHECKERBOARD[1]].T.reshape(-1, 2)
    objp *= SQUARE_SIZE

    objpoints = []  # 3D points
    imgpoints = []  # 2D points

    pipeline = build_pipeline(SCENE_CAMERA_ID, SCENE_WIDTH, SCENE_HEIGHT)
    cap = cv2.VideoCapture(pipeline, cv2.CAP_GSTREAMER)
    if not cap.isOpened():
        raise RuntimeError("Cannot open camera!")

    print("="*50)
    print("CALIBRATION MODE")
    print("="*50)
    print(f"Checkerboard inner corners: {CHECKERBOARD}")
    print(f"Square size: {SQUARE_SIZE}mm")
    print("")
    print("Controls:")
    print("  SPACE — capture frame (when corners detected)")
    print("  C     — run calibration (need 20+ frames)")
    print("  Q     — quit")
    print("")
    print("Hold checkerboard at different angles and distances")
    print("="*50)

    captured = 0
    img_count = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            continue

        gray    = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        display = frame.copy()

        # Try to find checkerboard
        found, corners = cv2.findChessboardCorners(
            gray, CHECKERBOARD,
            cv2.CALIB_CB_ADAPTIVE_THRESH +
            cv2.CALIB_CB_FAST_CHECK +
            cv2.CALIB_CB_NORMALIZE_IMAGE
        )

        if found:
            # Refine corners
            corners2 = cv2.cornerSubPix(
                gray, corners, (11,11), (-1,-1),
                (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
            )
            cv2.drawChessboardCorners(display, CHECKERBOARD, corners2, found)
            cv2.putText(display, f"DETECTED! SPACE to capture ({captured} captured)",
                (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,255,0), 2)
        else:
            cv2.putText(display, f"No checkerboard found ({captured} captured)",
                (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0,0,255), 2)

        cv2.putText(display, "SPACE=capture  C=calibrate  Q=quit",
            (20, display.shape[0]-20),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 1)

        cv2.imshow("Calibration", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break

        elif key == ord(' ') and found:
            objpoints.append(objp)
            imgpoints.append(corners2)
            captured += 1

            # Save image
            img_path = os.path.join(IMAGES_DIR, f"calib_{img_count:03d}.jpg")
            cv2.imwrite(img_path, frame)
            img_count += 1
            print(f"Captured frame {captured}")

        elif key == ord('c'):
            if captured < 10:
                print(f"Need at least 10 frames, have {captured}")
                continue

            print(f"\nRunning calibration with {captured} frames...")
            h, w = frame.shape[:2]

            ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(
                objpoints, imgpoints, (w, h), None, None
            )

            # Get optimal camera matrix
            newmtx, roi = cv2.getOptimalNewCameraMatrix(
                mtx, dist, (w,h), 1, (w,h)
            )

            print(f"\nCalibration RMS error: {ret:.4f}")
            print("(Good if < 1.0, excellent if < 0.5)")
            print(f"\nCamera Matrix:\n{mtx}")
            print(f"\nDistortion Coefficients:\n{dist}")

            # Save
            np.savez(SAVE_PATH,
                camera_matrix=mtx,
                dist_coeffs=dist,
                optimal_matrix=newmtx,
                roi=roi,
                rms_error=ret
            )
            print(f"\nSaved to: {SAVE_PATH}")

            # Show undistorted preview
            undistorted = cv2.undistort(frame, mtx, dist, None, newmtx)
            cv2.imshow("Original vs Undistorted", 
                np.hstack([frame, undistorted]))
            cv2.waitKey(3000)
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    calibrate()
