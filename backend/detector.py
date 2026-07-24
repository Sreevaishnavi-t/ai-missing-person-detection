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


def run_detection(
    source,
    stop_event=None,
    frame_callback=None,
    stop_on_match=False,
    confidence_threshold: float = 0.45,
    detect_every_n: int = 3,
    auto_screenshot: bool = True,
    min_face_size: int = 40
) -> None:
    """
    Main frame loop: reads video, skips frames for performance, detects faces,
    runs FAISS matching, logs matches, and streams annotated frames.

    Args:
        source:               cv2.VideoCapture source (0, 1, file path, RTSP URL).
        stop_event:           threading.Event polled each frame to stop cleanly.
        frame_callback:       callable(frame) called with each annotated frame.
        stop_on_match:        If True, stops detection after finding a match.
        confidence_threshold: Minimum similarity score required to trigger match.
        detect_every_n:       Frame skip count for face detection.
        auto_screenshot:      If True, saves frame snapshot to data/screenshots/.
        min_face_size:        Minimum face width/height in pixels for quality gate.
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
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    print(f"[Detector] Source FPS: {fps:.1f}  |  Detecting every {detect_every_n} frames "
          f"(~{fps / max(detect_every_n, 1):.1f} detections/sec) | Threshold: {confidence_threshold:.2f}")

    # ── 3. Detection loop ─────────────────────────────────────────────────────
    last_logged:  dict[str, float] = {}
    COOLDOWN_SECONDS = 10.0
    frame_index = 0
    # Store tuples of (face_bbox, label_str)
    last_annotations: list[tuple[any, str]] = []

    print("[Detector] Loop started. Send POST /stop to exit.")

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                print("[Detector] Stop signal received.")
                break

            ret, frame = cap.read()
            if not ret:
                print("[Detector] End of stream / failed to read frame.")
                break

            frame_index += 1

            # ── Face detection (every Nth frame only) ─────────────────────────
            if frame_index % detect_every_n == 0:
                last_faces = detect_faces(frame)
                new_annotations = []

                for face in last_faces:
                    try:
                        x1, y1, x2, y2 = face.bbox.astype(int)
                        w, h = x2 - x1, y2 - y1
                        # Quality gate: drop tiny/blurry faces
                        if w < min_face_size or h < min_face_size:
                            continue

                        embedding = get_embedding(face)
                        results = store.search(embedding, top_k=1)
                        label = ""

                        if results:
                            person_name, confidence = results[0]
                            if confidence >= confidence_threshold:
                                label = f"{person_name} ({confidence:.0%})"

                                now = time.time()
                                if person_name not in last_logged or (now - last_logged[person_name]) >= COOLDOWN_SECONDS:
                                    last_logged[person_name] = now

                                    screenshot_path_str = None
                                    if auto_screenshot:
                                        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                                        safe_name = person_name.replace(" ", "_").replace("/", "_")
                                        shot_path = SCREENSHOT_DIR / f"{safe_name}_{ts}.jpg"
                                        cv2.imwrite(str(shot_path), frame)
                                        screenshot_path_str = str(shot_path)

                                    log_match(
                                        person_name=person_name,
                                        confidence=confidence,
                                        screenshot_path=screenshot_path_str,
                                        video_source=str(source),
                                    )

                                    print(f"\n[ALERT] MATCH: {person_name}  |  confidence={confidence:.4f}\n")

                                    if stop_on_match and stop_event is not None:
                                        print("[Detector] Stop on match triggered. Stopping...")
                                        stop_event.set()

                        new_annotations.append((face.bbox.astype(int), label))
                    except Exception as e:
                        print(f"[Detector] Face process error: {e}")
                        continue

                last_annotations = new_annotations

            # ── Draw bounding boxes and text labels ───────────────────────────
            for (x1, y1, x2, y2), label in last_annotations:
                try:
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                    if label:
                        cv2.putText(
                            frame,
                            label,
                            (x1, max(y1 - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX,
                            0.6,
                            (0, 255, 0),
                            2
                        )
                except Exception:
                    pass

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
