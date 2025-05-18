import os
from pathlib import Path

QRIS_STATIC = os.getenv("QRIS_STATIC", "")
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost/restaurant")

STATIC_DIR = Path("static")
MENU_IMG_DIR = STATIC_DIR / "menu"
