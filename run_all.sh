#!/bin/bash
echo "================================================"
echo "  People Analytics System"
echo "================================================"

sudo nvpmodel -m 0
sudo jetson_clocks

PROJECT_DIR="/home/vision/projects/people-analytics"
export PYTHONPATH="$PROJECT_DIR"
cd $PROJECT_DIR

echo "[0] Restarting argus daemon.."
sudo systemctl restart nvargus-daemon
sleep 5

echo "[1] Initializing database..."
python3 shared/database.py

echo "[2] Starting Scene Detector..."
python3 scene/detector.py &
SCENE_PID=$!
echo "    PID: $SCENE_PID"

# Wait for scene detector to fully initialize before starting face
echo "    Waiting for scene detector to initialize..."
sleep 10

echo "[3] Starting Face Analytics..."
python3 face/analytics.py &
FACE_PID=$!
echo "    PID: $FACE_PID"

sleep 5

echo "[4] Starting Dashboard..."
python3 dashboard/app.py &
DASH_PID=$!
echo "    PID: $DASH_PID"

echo "[5] Starting Ad Viewer..."
python3 adviewer/app.py &
AD_PID=$!
echo "    PID: $AD_PID"

echo ""
echo "================================================"
echo "  Dashboard:  http://$(hostname -I | cut -d' ' -f1):5000"
echo "  Ad Viewer:  http://$(hostname -I | cut -d' ' -f1):5001"
echo "  Press Ctrl+C to stop"
echo "================================================"

trap "echo 'Stopping...'; kill $SCENE_PID $FACE_PID $DASH_PID $AD_PID 2>/dev/null; exit" INT TERM
wait
