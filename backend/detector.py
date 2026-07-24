import os
import time
import datetime
import cv2
import numpy as np

from backend.config import CONFIDENCE_THRESHOLD, SCREENSHOT_DIR, DB_PATH
from backend.embedder import detect_faces, get_embedding
from backend.faiss_store import FAISSStore
from backend.logger import log_match

# ==============================================================================
# Frame-skip strategy
# ==============================================================================
# InsightFace (buffalo_l) takes ~80–200 ms per frame on CPU.
# A 30fps video produces a frame every 33 ms — so running face detection on
# every frame means the detection thread falls 6–10x behind real-time, causing:
#   • The stream to appear frozen or jerky (latest_frame updates too slowly)
#   • High CPU usage (>90% on a single core)
#   • Missed frames being dropped silently
#
# Solution: run InsightFace only on every DETECT_EVERY_N frames.
# All other frames are passed straight to the frame_callback (for streaming)
# without any face analysis.  This keeps the stream smooth at real-time speed
# while still detecting faces at ~5–10 fps — more than enough for a walking person.
#
# DETECT_EVERY_N = 3  →  10fps detection from a 30fps source (good balance)
# DETECT_EVERY_N = 6  →  5fps detection  (better for slow machines)
# ==============================================================================
DETECT_EVERY_N = 3


def run_detection(source, stop_event=None, frame_callback=None, stop_on_match=False) -> None:
    """
    Main frame loop: reads video, skips frames for performance, detects faces,
    runs FAISS matching, logs matches, and streams annotated frames.

    Args:
        source:         cv2.VideoCapture source — integer (webcam index) or
                        string (video file path / RTSP URL).
        stop_event:     threading.Event polled each frame; set it to stop cleanly.
        frame_callback: callable(frame: np.ndarray) — called with every annotated
                        frame so the /stream endpoint can serve it.
        stop_on_match:  If True, triggers stop_event and exits after finding a match.
    """

    # ── 1. Load FAISS watchlist ───────────────────────────────────────────────
    store = FAISSStore()
    db_path_str = str(DB_PATH)
    if os.path.exists(db_path_str):
        print(f"[Detector] Loading FAISS index from {db_path_str}…")
        try:
            store.load_index(db_path_str)
            print(f"[Detector] Watchlist loaded — {len(store.names)} person(s) enrolled.")
        except Exception as exc:
            print(f"[Detector] Could not load FAISS index: {exc}. Starting empty.")
    else:
        print("[Detector] No FAISS index found — detection will run but no matches possible.")

    # ── 2. Open video source ──────────────────────────────────────────────────
    print(f"[Detector] Opening source: {source!r}")
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        print(f"[Detector] ERROR: Could not open video source: {source!r}")
        print("[Detector] Possible causes:")
        print("  • Webcam index wrong — try 0 or 1")
        print("  • Video file path has a typo or the file doesn't exist")
        print("  • File path contains special characters — try copying the exact path")
        return

    # Read actual FPS from the source for informational logging
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    print(f"[Detector] Source FPS: {fps:.1f}  |  Detecting every {DETECT_EVERY_N} frames "
          f"(~{fps / DETECT_EVERY_N:.1f} detections/sec)")

    # ── 3. Detection loop ─────────────────────────────────────────────────────
    last_logged:  dict[str, float] = {}
    COOLDOWN_SECONDS = 10.0
    frame_index = 0
    # Keep the last detected faces so we can draw boxes on skipped frames too
    last_faces: list = []

    print("[Detector] Loop started. Send POST /stop to exit.")

    try:
        while True:
            # ── Stop signal check ─────────────────────────────────────────────
            if stop_event is not None and stop_event.is_set():
                print("[Detector] Stop signal received.")
                break

            # ── Read frame ────────────────────────────────────────────────────
            ret, frame = cap.read()
            if not ret:
                print("[Detector] End of stream / failed to read frame.")
                break

            frame_index += 1

            # ── Face detection (every Nth frame only) ─────────────────────────
            if frame_index % DETECT_EVERY_N == 0:
                last_faces = detect_faces(frame)

                for face in last_faces:
                    # Extract embedding — skip if fallback mode (no InsightFace)
                    try:
                        embedding = get_embedding(face)
                    except RuntimeError:
                        continue

                    # FAISS similarity search
                    results = store.search(embedding, top_k=1)
                    if not results:
                        continue

                    person_name, confidence = results[0]

                    if confidence < CONFIDENCE_THRESHOLD:
                        continue

                    # ── Cooldown check ────────────────────────────────────────
                    now = time.time()
                    if person_name in last_logged and \
                            (now - last_logged[person_name]) < COOLDOWN_SECONDS:
                        continue

                    last_logged[person_name] = now

                    # ── Save screenshot ───────────────────────────────────────
                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    # Sanitise name for filesystem (replace spaces and slashes)
                    safe_name = person_name.replace(" ", "_").replace("/", "_")
                    screenshot_path = SCREENSHOT_DIR / f"{safe_name}_{ts}.jpg"
                    cv2.imwrite(str(screenshot_path), frame)

                    # ── Log to SQLite ─────────────────────────────────────────
                    log_match(
                        person_name=person_name,
                        confidence=confidence,
                        screenshot_path=str(screenshot_path),
                        video_source=str(source),
                    )

                    print(f"\n[ALERT] MATCH: {person_name}  |  "
                          f"confidence={confidence:.4f}  |  {screenshot_path.name}\n")

                    if stop_on_match and stop_event is not None:
                        print("[Detector] Stop on match triggered. Stopping...")
                        stop_event.set()
                        break

            # ── Draw bounding boxes on all detected faces ─────────────────────
            for face in last_faces:
                try:
                    x1, y1, x2, y2 = face.bbox.astype(int)
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    # Optionally label the box — would need to track which face
                    # matched which name, left simple for now
                except Exception:
                    pass

            # ── Push frame to stream ──────────────────────────────────────────
            if frame_callback is not None:
                try:
                    frame_callback(frame)
                except Exception as exc:
                    print(f"[Detector] frame_callback error: {exc}")

    finally:
        cap.release()
        try:
            cv2.destroyAllWindows()
        except Exception:
            pass
        print("[Detector] Released video source.")
