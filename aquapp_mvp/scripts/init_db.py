from __future__ import annotations

from app.db import init_db


if __name__ == "__main__":
    init_db()
    print("Database initialized.")
