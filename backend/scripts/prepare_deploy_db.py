"""Prepare a self-contained deploy.db from simulator.db for the container.

The dev database runs in WAL mode, so simulator.db-wal may hold the newest
frames. Fold them into the main file (PRAGMA wal_checkpoint TRUNCATE), refresh
query statistics (ANALYZE), then copy to deploy.db so the image ships a single
frozen snapshot that needs no sidecar files.

Usage (from backend/):
    python scripts/prepare_deploy_db.py [--source simulator.db] [--dest deploy.db]

Pure stdlib: no project imports, so it runs in any Python 3 environment.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def prepare(source: Path, dest: Path) -> dict:
    if not source.is_file():
        raise FileNotFoundError(f"source database not found: {source}")

    conn = sqlite3.connect(source)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.execute("ANALYZE")
        conn.commit()
    finally:
        conn.close()

    shutil.copy2(source, dest)
    return {
        "source": str(source),
        "dest": str(dest),
        "size": dest.stat().st_size,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", default=str(BACKEND_DIR / "simulator.db"))
    parser.add_argument("--dest", default=str(BACKEND_DIR / "deploy.db"))
    args = parser.parse_args(argv)

    info = prepare(Path(args.source), Path(args.dest))
    print(f"copied {info['source']} -> {info['dest']} ({info['size']} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())