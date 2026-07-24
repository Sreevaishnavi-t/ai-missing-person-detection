"""
backend/main.py — FastAPI REST API for the AI Missing Person Detection System

Design Overview
---------------
This file wires together all four Phase 1-3 modules (embedder, faiss_store,
detector, logger) behind a clean HTTP interface that the React frontend can
consume.  Every non-trivial design choice is documented inline.
"""

import io
import json
import threading
import datetime
import os
from pathlib import Path

import cv2
import numpy as np
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from contextlib import asynccontextmanager

from backend.config import DB_PATH, SCREENSHOT_DIR, WATCHLIST_DIR
from backend.embedder import detect_faces, get_embedding
from backend.faiss_store import FAISSStore
from backend.detector import run_detection
from backend.logger import get_recent_matches, delete_all_matches, update_match_status
from pydantic import BaseModel

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB limit
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "*").split(",")
API_KEY = os.getenv("API_KEY", "")

def verify_api_key(x_api_key: str | None = Header(None)):
    """Validates X-API-Key header if API_KEY environment variable is configured."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key header (X-API-Key).")

class StartRequest(BaseModel):
    source: int | str = 0
    stop_on_match: bool = False
    confidence_threshold: float = 0.45
    detect_every_n: int = 3
    auto_screenshot: bool = True

# ==============================================================================
# METADATA FILE
# ==============================================================================
# FAISS stores only raw vectors and assigns sequential integer IDs (0, 1, 2, …).
# It has no column for "enrolled_at" timestamps.  We keep a sidecar JSON file
# that maps each FAISS index position → { name, enrolled_at }.
# This is the same pattern as faiss_store.py's names list, but richer.
#
# The test suite imports METADATA_PATH directly to clean state between runs,
# so we expose it at module level.
METADATA_PATH = DB_PATH.parent / "watchlist_metadata.json"


def _load_metadata() -> list:
    """Return the list of enrolled persons from the metadata JSON file."""
    if METADATA_PATH.exists():
        with open(METADATA_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_metadata(entries: list) -> None:
    """Persist the metadata list to disk."""
    METADATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(METADATA_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2)


# ==============================================================================
# GLOBAL APPLICATION STATE
# ==============================================================================
# FastAPI's app.state is a simple namespace attached to the application object.
# We store mutable runtime state here so all endpoint functions share it.
#
# detection_thread  — the background Thread object while detection is running
# stop_event        — threading.Event the thread polls; .set() causes it to exit
# faiss_store       — the in-memory FAISSStore loaded at startup
# latest_frame      — the most recent annotated BGR frame produced by the detector
# frame_lock        — protects latest_frame from concurrent read/write races
# ==============================================================================

# We define a small container so we can annotate types clearly.
class _AppState:
    detection_thread: threading.Thread | None = None
    stop_event: threading.Event | None = None
    faiss_store: FAISSStore | None = None
    latest_frame: np.ndarray | None = None
    frame_lock: threading.Lock = threading.Lock()


# ==============================================================================
# LIFESPAN HANDLER
# ==============================================================================
# FastAPI's lifespan replaces the deprecated @app.on_event("startup") pattern.
# Code before the `yield` runs at startup; code after runs at shutdown.
#
# Design decision — load FAISS at startup, not per-request:
#   Loading the binary index from disk takes ~50–200 ms and deserialises several
#   MB of data.  Doing this on every search request would add unacceptable latency
#   and waste CPU.  Loading once at startup keeps the index hot in memory and makes
#   every subsequent search O(1) in terms of I/O.
# ==============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── STARTUP ──────────────────────────────────────────────────────────────
    # When the server starts for real (uvicorn), reload the FAISS index fresh
    # from disk and overwrite the module-level defaults set below.
    store = FAISSStore()
    if DB_PATH.exists():
        print("[Startup] Loading FAISS index from disk…")
        try:
            store.load_index(str(DB_PATH))
            print(f"[Startup] FAISS index loaded — {store.index.ntotal} person(s) enrolled.")
        except Exception as exc:
            print(f"[Startup] Warning: could not load FAISS index: {exc}")
    else:
        print("[Startup] No FAISS index found — starting with an empty store.")

    app.state.faiss_store = store
    app.state.detection_thread = None
    app.state.stop_event = None
    app.state.latest_frame = None
    app.state.frame_lock = threading.Lock()

    yield  # ← application runs while we are suspended here

    # ── SHUTDOWN ─────────────────────────────────────────────────────────────
    if app.state.stop_event is not None:
        app.state.stop_event.set()
    if app.state.detection_thread is not None:
        app.state.detection_thread.join(timeout=5)
    print("[Shutdown] Application shutdown complete.")


# ==============================================================================
# APPLICATION SETUP
# ==============================================================================
# title / description / version appear in the auto-generated /docs (Swagger UI)
# and /redoc pages that FastAPI generates for free.
# ==============================================================================
app = FastAPI(
    title="AI Missing Person Detection API",
    description=(
        "REST API for enrolling missing persons, running real-time video detection, "
        "streaming live MJPEG video, and querying match logs."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ==============================================================================
# MODULE-LEVEL STATE DEFAULTS
# ==============================================================================
# FastAPI's TestClient may not always trigger the lifespan context manager
# depending on how it's invoked.  We initialise all state keys here as safe
# defaults so every endpoint function can rely on them existing.
#
# The lifespan handler overwrites these with the real loaded values at startup.
# In tests that don't go through lifespan, the FAISSStore is created fresh
# (empty) on the first request that needs it.
# ==============================================================================
app.state.detection_thread = None
app.state.stop_event = None
app.state.latest_frame = None
app.state.frame_lock = threading.Lock()

# Eagerly load the FAISS store at import time as well, so the state is always
# populated even when the lifespan handler hasn't run (e.g., unit tests).
_startup_store = FAISSStore()
if DB_PATH.exists():
    try:
        _startup_store.load_index(str(DB_PATH))
    except Exception:
        pass  # start with an empty store if load fails
app.state.faiss_store = _startup_store

# ==============================================================================
# CORS MIDDLEWARE
# ==============================================================================
# CORS (Cross-Origin Resource Sharing) is a browser security mechanism.
#
# By default, browsers block JavaScript running on one origin (e.g.,
# http://localhost:3000 — your React dev server) from making HTTP requests
# to a *different* origin (e.g., http://localhost:8000 — this FastAPI server).
# This is the "same-origin policy".
#
# To allow our React frontend to call these endpoints, the server must respond
# with specific HTTP headers (Access-Control-Allow-Origin, etc.) telling the
# browser "this cross-origin request is permitted."
#
# allow_origins=["*"]  — permits every origin.  Fine for local development.
# In production we would replace "*" with the exact frontend domain
# (e.g., "https://myapp.com") to prevent other websites from calling our API.
#
# allow_methods / allow_headers — must include the methods and headers the
# frontend actually uses.  ["*"] is the simplest development setting.
# ==============================================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True if "*" not in ALLOWED_ORIGINS else False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==============================================================================
# ENDPOINT 1 — POST /enroll
# ==============================================================================
@app.post("/enroll", dependencies=[Depends(verify_api_key)])
def enroll_person(
    file: UploadFile = File(..., description="JPEG/PNG reference photo of the person"),
    name: str = Form(..., description="Full name of the missing person"),
):
    """Enroll a new person into the watchlist by uploading a single-face photo."""

    # ── 1. Read raw bytes and decode to BGR numpy array ──────────────────────
    image_bytes = file.file.read()
    if len(image_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail="File size exceeds maximum allowed limit of 10MB.",
        )

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)

    if image_bgr is None:
        raise HTTPException(
            status_code=400,
            detail="Could not decode image. Please upload a valid JPEG or PNG file.",
        )

    # ── 2. Face detection ─────────────────────────────────────────────────────
    faces = detect_faces(image_bgr)

    if len(faces) == 0:
        raise HTTPException(
            status_code=400,
            detail="No face detected in the uploaded image. Please upload a clear, front-facing photo.",
        )

    if len(faces) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"Multiple faces detected ({len(faces)} faces found). Please upload a photo with exactly one person.",
        )

    # ── 3. Extract embedding ──────────────────────────────────────────────────
    try:
        embedding = get_embedding(faces[0])
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=f"Embedding extraction failed: {exc}")

    # ── 4. Determine the new FAISS index ID ──────────────────────────────────
    # We derive the next ID from the metadata file, not from store.index.ntotal.
    # The in-memory store may have been loaded at import time from a previous
    # run's disk state; if the test suite deleted those files and reset metadata
    # the ntotal count would be stale.  The metadata list is always authoritative
    # because clean_state() deletes METADATA_PATH before each test run, making
    # len(metadata) == 0 on a fresh start.
    store: FAISSStore = app.state.faiss_store

    # If the on-disk FAISS index no longer exists (deleted by test clean_state),
    # reset the in-memory store so ntotal matches the empty-disk reality.
    if not DB_PATH.exists() and store.index.ntotal > 0:
        store.index.reset()
        store.names.clear()

    new_id = len(_load_metadata())  # next sequential 0-based ID

    # ── 5. Save image to watchlist directory ─────────────────────────────────
    # Use a sanitised filename: replace spaces with underscores, keep the
    # original extension if available, fall back to .jpg.
    original_ext = Path(file.filename).suffix if file.filename else ".jpg"
    safe_name = name.replace(" ", "_")
    save_filename = f"{safe_name}_{new_id}{original_ext}"
    save_path = WATCHLIST_DIR / save_filename
    with open(save_path, "wb") as out_f:
        out_f.write(image_bytes)

    # ── 6. Add to in-memory FAISS store and persist to disk ──────────────────
    store.add(name, embedding)
    store.save_index(str(DB_PATH))

    # ── 7. Record enriched metadata (name + timestamp) ───────────────────────
    enrolled_at = datetime.datetime.utcnow().isoformat() + "Z"
    metadata = _load_metadata()
    metadata.append({"id": new_id, "name": name, "enrolled_at": enrolled_at})
    _save_metadata(metadata)

    return {"id": new_id, "name": name, "enrolled_at": enrolled_at}


# ==============================================================================
# ENDPOINT 2 — GET /watchlist
# ==============================================================================
@app.get("/watchlist")
def get_watchlist():
    """Return all enrolled persons with their IDs and enrollment timestamps."""
    return _load_metadata()


# ==============================================================================
# ENDPOINT 2b — DELETE /watchlist/{id}
# ==============================================================================
# Removes a person from the watchlist by their metadata ID.
#
# FAISS does not support removing individual vectors from a flat index.
# The standard workaround is to rebuild the index from scratch using only
# the surviving entries.  This is acceptable because:
#   1. Enrollment is infrequent — deletions are rare operational events.
#   2. Watchlists are small (hundreds, not millions) so a full rebuild
#      takes milliseconds.
#
# Steps:
#   1. Remove the entry from the metadata JSON sidecar.
#   2. Re-assign sequential IDs to the remaining entries (fill the gap).
#   3. Rebuild the FAISS index from scratch by re-reading each watchlist
#      image file and re-extracting embeddings.
#   4. Save the rebuilt index and updated metadata to disk.
# ==============================================================================
@app.delete("/watchlist/{person_id}", dependencies=[Depends(verify_api_key)])
def delete_from_watchlist(person_id: int):
    """Remove an enrolled person from the watchlist by ID."""
    metadata = _load_metadata()

    # Find the entry
    entry = next((e for e in metadata if e["id"] == person_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Person with ID {person_id} not found.")

    # Remove from metadata list
    metadata = [e for e in metadata if e["id"] != person_id]

    # Re-assign sequential IDs to close the gap left by the deleted entry
    for i, e in enumerate(metadata):
        e["id"] = i

    # Rebuild FAISS index from scratch using surviving watchlist images
    store: FAISSStore = app.state.faiss_store
    store.index.reset()
    store.names.clear()

    for e in metadata:
        # Find the corresponding watchlist image (matches name_id.ext pattern)
        safe_name = e["name"].replace(" ", "_")
        # Search for any file matching this person's name prefix
        candidates = list(WATCHLIST_DIR.glob(f"{safe_name}_*.jpg")) + \
                     list(WATCHLIST_DIR.glob(f"{safe_name}_*.jpeg")) + \
                     list(WATCHLIST_DIR.glob(f"{safe_name}_*.png")) + \
                     list(WATCHLIST_DIR.glob(f"{safe_name}_*.webp"))
        if not candidates:
            # Skip if image is missing — person stays in metadata but won't match
            store.names.append(e["name"])
            continue
        img_path = candidates[0]
        img_bgr = cv2.imread(str(img_path))
        if img_bgr is None:
            store.names.append(e["name"])
            continue
        faces = detect_faces(img_bgr)
        if not faces:
            store.names.append(e["name"])
            continue
        try:
            emb = get_embedding(faces[0])
            store.add(e["name"], emb)
        except RuntimeError:
            store.names.append(e["name"])

    # Persist updated index and metadata
    if store.index.ntotal > 0:
        store.save_index(str(DB_PATH))
    elif DB_PATH.exists():
        DB_PATH.unlink()
        DB_PATH.with_suffix(".json").unlink(missing_ok=True)

    _save_metadata(metadata)
    return {"status": "deleted", "id": person_id}


@app.post("/watchlist/{person_id}/photos", dependencies=[Depends(verify_api_key)])
def add_person_photo(
    person_id: int,
    file: UploadFile = File(..., description="Additional JPEG/PNG reference photo"),
):
    """Add a secondary reference photo for an existing enrolled person."""
    metadata = _load_metadata()
    person = next((p for p in metadata if p["id"] == person_id), None)
    if not person:
        raise HTTPException(status_code=404, detail=f"Person with ID {person_id} not found.")

    image_bytes = file.file.read()
    if len(image_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=400, detail="File size exceeds maximum allowed limit of 10MB.")

    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image_bgr = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image_bgr is None:
        raise HTTPException(status_code=400, detail="Could not decode image.")

    faces = detect_faces(image_bgr)
    if len(faces) != 1:
        raise HTTPException(status_code=400, detail="Photo must contain exactly one face.")

    emb = get_embedding(faces[0])

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = person["name"].replace(" ", "_")
    photo_path = WATCHLIST_DIR / f"{safe_name}_extra_{ts}.jpg"
    cv2.imwrite(str(photo_path), image_bgr)

    store = app.state.faiss_store or FAISSStore()
    store.add(person["name"], emb)
    store.save_index(str(DB_PATH))

    return {"status": "added", "person_name": person["name"], "photo_path": str(photo_path)}


@app.post("/rebuild-index", dependencies=[Depends(verify_api_key)])
def rebuild_index():
    """Rebuild the FAISS index by re-scanning data/watchlist/ photos."""
    if app.state.detection_thread is not None and app.state.detection_thread.is_alive():
        raise HTTPException(status_code=409, detail="Stop detection before rebuilding the FAISS index.")

    store = app.state.faiss_store or FAISSStore()
    metadata = _load_metadata()
    store.index.reset()
    store.names.clear()

    count = 0
    for e in metadata:
        safe_name = e["name"].replace(" ", "_")
        candidates = (
            list(WATCHLIST_DIR.glob(f"{safe_name}_*.jpg")) +
            list(WATCHLIST_DIR.glob(f"{safe_name}_*.jpeg")) +
            list(WATCHLIST_DIR.glob(f"{safe_name}_*.png")) +
            list(WATCHLIST_DIR.glob(f"{safe_name}_*.webp"))
        )
        if not candidates:
            continue
        for img_path in candidates:
            img_bgr = cv2.imread(str(img_path))
            if img_bgr is None:
                continue
            faces = detect_faces(img_bgr)
            if not faces:
                continue
            try:
                emb = get_embedding(faces[0])
                store.add(e["name"], emb)
                count += 1
            except Exception:
                pass

    if store.index.ntotal > 0:
        store.save_index(str(DB_PATH))
    app.state.faiss_store = store
    return {"status": "rebuilt", "enrolled_faces": count, "message": f"FAISS index rebuilt with {count} face embedding(s)."}


# ==============================================================================
# ENDPOINT 3 — POST /start
# ==============================================================================
@app.post("/start", dependencies=[Depends(verify_api_key)])
def start_detection(body: StartRequest):
    """
    Start the background detection loop.
    """
    source_raw = body.source

    if isinstance(source_raw, str) and source_raw.isdigit():
        source = int(source_raw)
    else:
        source = source_raw

    if (
        app.state.detection_thread is not None
        and app.state.detection_thread.is_alive()
    ):
        raise HTTPException(status_code=409, detail="Detection is already running.")

    stop_event = threading.Event()
    app.state.stop_event = stop_event

    def _frame_callback(frame: np.ndarray):
        with app.state.frame_lock:
            app.state.latest_frame = frame.copy()

    thread = threading.Thread(
        target=run_detection,
        args=(source,),
        kwargs={
            "stop_event": stop_event,
            "frame_callback": _frame_callback,
            "stop_on_match": body.stop_on_match,
            "confidence_threshold": body.confidence_threshold,
            "detect_every_n": body.detect_every_n,
            "auto_screenshot": body.auto_screenshot,
        },
        daemon=True,
        name="DetectionThread",
    )
    thread.start()
    app.state.detection_thread = thread

    return {"status": "started"}


# ==============================================================================
# ENDPOINT 4 — POST /stop
# ==============================================================================
# We signal the thread via stop_event.set() and then join() to wait for it to
# finish releasing the camera.  We use a timeout so the API call doesn't hang
# forever if the thread is stuck (e.g., waiting on a network stream).
# ==============================================================================
@app.post("/stop", dependencies=[Depends(verify_api_key)])
def stop_detection():
    """Signal the detection thread to stop and wait for it to finish."""
    if app.state.stop_event is None or app.state.detection_thread is None:
        raise HTTPException(status_code=400, detail="No detection is currently running.")

    app.state.stop_event.set()
    app.state.detection_thread.join(timeout=10)

    app.state.detection_thread = None
    app.state.stop_event = None

    with app.state.frame_lock:
        app.state.latest_frame = None

    return {"status": "stopped"}


@app.get("/status")
def get_status():
    """Returns whether the background detection thread is currently running."""
    is_running = False
    if app.state.detection_thread is not None:
        is_running = app.state.detection_thread.is_alive()
    return {"is_running": is_running}


@app.get("/results")
def get_results(limit: int = 50):
    """Return the most recent detection matches, newest first."""
    matches = get_recent_matches(limit=limit)

    for match in matches:
        raw_path = match.get("screenshot_path", "")
        if raw_path:
            filename = Path(raw_path).name
            match["screenshot_url"] = f"/screenshots/{filename}"
        else:
            match["screenshot_url"] = None

    return matches


@app.delete("/results/all", dependencies=[Depends(verify_api_key)])
def clear_all_results():
    """Delete every match record from the SQLite database."""
    count = delete_all_matches()
    return {"status": "cleared", "deleted": count}


class StatusUpdate(BaseModel):
    status: str

@app.patch("/results/{match_id}", dependencies=[Depends(verify_api_key)])
def update_result_status(match_id: int, payload: StatusUpdate):
    """Updates the status of a specific match (e.g. pending -> approved)."""
    valid_statuses = ["pending", "approved", "rejected"]
    if payload.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {valid_statuses}")
    
    updated = update_match_status(match_id, payload.status)
    if not updated:
        raise HTTPException(status_code=404, detail="Match not found.")
    
    # Re-attach screenshot_url
    raw_path = updated.get("screenshot_path", "")
    filename = Path(raw_path).name
    updated["screenshot_url"] = f"/screenshots/{filename}"
    
    return updated


# ==============================================================================
# ENDPOINT 6 — GET /stream   (MJPEG live video)
# ==============================================================================
# What is MJPEG streaming?
# ─────────────────────────
# MJPEG (Motion JPEG) is the simplest possible live video protocol.  Instead of
# encoding motion between frames (like H.264/H.265), it sends a sequence of
# independent JPEG images separated by HTTP multipart boundaries.
#
# The HTTP Content-Type is:
#   multipart/x-mixed-replace; boundary=frame
#
# Each "part" in the stream looks like:
#   --frame\r\n
#   Content-Type: image/jpeg\r\n
#   \r\n
#   <raw JPEG bytes>
#   \r\n
#
# The browser's <img src="/stream"> tag natively understands this format and
# automatically repaints the image each time a new JPEG part arrives, creating
# the appearance of live video — no JavaScript required.
#
# Design decision — generator + StreamingResponse:
#   FastAPI's StreamingResponse accepts a Python generator.  We yield one JPEG
#   part per iteration, which keeps memory usage constant regardless of how
#   long the stream runs (we never buffer the whole video in RAM).
#
# Design decision — latest_frame vs a queue:
#   We store only the single most-recent frame under a lock.  If the client
#   reads slower than detection produces frames, it just gets the latest one —
#   there is no back-pressure or frame queue.  This is correct for live
#   monitoring where staleness is worse than dropped frames.
# ==============================================================================
@app.get("/stream")
def stream_video():
    """Stream live MJPEG video from the running detection loop."""

    def _mjpeg_generator():
        # Yield MJPEG frames continuously until the browser disconnects.
        #
        # When the browser closes the tab or navigates away, the ASGI server
        # cancels the response task, which raises GeneratorExit here — that's
        # our only exit signal in production.  No frame cap, no thread check.
        #
        # We sleep briefly between frames so this loop doesn't spin at 100%
        # CPU when the detection thread is slower than the stream consumer.
        import time as _time
        try:
            while True:
                with app.state.frame_lock:
                    frame = app.state.latest_frame

                if frame is None:
                    # Detection not started yet — send a black placeholder
                    # so the browser keeps the connection open
                    placeholder = np.zeros((240, 320, 3), dtype=np.uint8)
                    success, jpeg = cv2.imencode(".jpg", placeholder)
                    _time.sleep(0.05)   # 20fps poll while waiting
                else:
                    success, jpeg = cv2.imencode(
                        ".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80]
                    )
                    _time.sleep(0.033)  # ~30fps cap — don't flood the browser

                if success:
                    yield (
                        b"--frame\r\n"
                        b"Content-Type: image/jpeg\r\n\r\n"
                        + jpeg.tobytes()
                        + b"\r\n"
                    )

        except GeneratorExit:
            # Browser disconnected — clean exit, no error
            pass

    return StreamingResponse(
        _mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


# ==============================================================================
# ENDPOINT 7 — GET /screenshots/{filename}
# ==============================================================================
# Serves static screenshot files directly from the data/screenshots/ directory.
#
# Design decision — FileResponse vs StaticFiles mount:
#   We use a parametric FileResponse endpoint rather than mounting a
#   StaticFiles directory because:
#   1. We can validate the filename and return a proper 404 JSON error.
#   2. We can control which files are served (only .jpg/.png) preventing
#      directory traversal attacks by rejecting filenames with path separators.
# ==============================================================================
@app.get("/screenshots/{filename}")
def serve_screenshot(filename: str):
    """Serve a saved screenshot image by filename."""

    # Security: reject filenames that try to traverse directories
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    file_path = SCREENSHOT_DIR / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Screenshot '{filename}' not found.")

    return FileResponse(path=str(file_path), media_type="image/jpeg")
