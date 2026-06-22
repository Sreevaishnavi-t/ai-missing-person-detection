from pathlib import Path

# BASE_DIR is the absolute path to the project root folder: missing-person-ai/.
BASE_DIR = Path(__file__).resolve().parent.parent

# CONFIDENCE_THRESHOLD is the minimum similarity score we will accept as a likely face match.
CONFIDENCE_THRESHOLD = 0.45

# WATCHLIST_DIR stores reference photos for people we want to search for.
WATCHLIST_DIR = BASE_DIR / "data" / "watchlist"

# SCREENSHOT_DIR stores webcam/frame snapshots when the system finds a useful detection.
SCREENSHOT_DIR = BASE_DIR / "data" / "screenshots"

# DB_PATH is where the FAISS vector index file will be saved in a later phase.
DB_PATH = BASE_DIR / "data" / "db" / "faiss_index.bin"

# DB_SQLITE_PATH is where the SQLite database for match logs is stored.
DB_SQLITE_PATH = BASE_DIR / "data" / "db" / "matches.db"

# Ensure the Phase 1 and 3 data folders exist before other code tries to read or write them.
for directory in (WATCHLIST_DIR, SCREENSHOT_DIR, DB_PATH.parent):
    directory.mkdir(parents=True, exist_ok=True)
