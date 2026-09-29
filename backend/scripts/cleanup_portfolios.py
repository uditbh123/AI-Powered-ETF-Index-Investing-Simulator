"""Delete portfolios (and everything they own) to leave a clean Portfolios list.

Wipes the developer/test portfolios that accumulate from smoke tests, curl
checks and manual pokes, so a user study starts from an empty slate instead of
32 rows called "My Portfolio".

Usage (from backend/):
    # Preview. This is the default: nothing is written without --apply.
    python scripts/cleanup_portfolios.py

    # Actually delete, after showing the plan.
    python scripts/cleanup_portfolios.py --apply

    # Only portfolios whose name contains a substring.
    python scripts/cleanup_portfolios.py --name "Smoke" --apply

    # The frozen snapshot the container ships, not just the dev database.
    python scripts/cleanup_portfolios.py --db deploy.db --apply

    # Also reset the portfolios id counter so the first study portfolio is
    # id 1 again. Only valid when the table ends up empty.
    python scripts/cleanup_portfolios.py --reset-sequence --apply

Deliberately reuses ``app.dao.portfolios.delete_portfolio`` instead of writing
its own DELETE statements. That function owns the dependency order
(simulation_results -> simulation_runs -> portfolio_holdings -> portfolios) and
the schema declares those FKs without ON DELETE CASCADE, so an out-of-order or
partial delete either fails on the FK constraint or orphans rows. Reusing it
means this script cannot drift from the order the app enforces.
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.dao.portfolios import delete_portfolio  # noqa: E402

#: Tables whose contents are wiped as a side effect. Not touched: users, tickers,
#: prices, news_sentiment. A study still needs the catalog, the price history and
#: the sentiment corpus to be intact.
OWNED_TABLES = ("simulation_results", "simulation_runs", "portfolio_holdings")


def connect(path: Path) -> sqlite3.Connection:
    """Open the database with foreign keys enforced, like the app does.

    ``database.get_connection`` sets this per connection. Without it the
    dependency ordering inside ``delete_portfolio`` is never actually tested by
    the FK engine, so a bug there would pass silently here.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def schema_fingerprint(conn: sqlite3.Connection) -> list[tuple[str, str]]:
    """(table, CREATE statement) for every table, for before/after comparison."""
    rows = conn.execute(
        "SELECT name, COALESCE(sql, '') FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def table_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts = {}
    for (name,) in conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
    ):
        counts[name] = conn.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
    return counts


def find_portfolios(conn: sqlite3.Connection, name_filter: str | None) -> list[sqlite3.Row]:
    if name_filter:
        # Parameterised, and the LIKE wildcards are escaped so a filter is a
        # literal substring match rather than a pattern the caller half-controls.
        pattern = (
            name_filter.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        )
        return conn.execute(
            "SELECT id, name, monthly_contribution FROM portfolios "
            "WHERE name LIKE ? ESCAPE '\\' ORDER BY id",
            (f"%{pattern}%",),
        ).fetchall()
    return conn.execute(
        "SELECT id, name, monthly_contribution FROM portfolios ORDER BY id"
    ).fetchall()


def backup(path: Path) -> Path:
    """Copy the database aside, folding any WAL frames into the main file first.

    The dev database runs in WAL mode, so simulator.db-wal can hold committed
    rows that are not yet in simulator.db. Copying the main file alone would
    produce a backup that silently restores stale data.
    """
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    # Timestamp in the middle, ".db" last, so the existing `*.db` ignore rule
    # covers backups. A `simulator.db.bak-<stamp>` name does NOT match `*.db`
    # and would show up as an untracked 8 MB file, one `git add -A` away from
    # being committed.
    dest = path.with_name(f"{path.stem}.bak-{stamp}{path.suffix}")
    shutil.copy2(path, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join(__doc__.splitlines()[1:]),
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=BACKEND_DIR / "simulator.db",
        help="database to clean (default: simulator.db)",
    )
    parser.add_argument(
        "--name",
        help="only portfolios whose name contains this substring (default: all)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="actually delete; without this the script only prints the plan",
    )
    parser.add_argument(
        "--reset-sequence",
        action="store_true",
        help="reset the portfolios id counter (requires the table to end up empty)",
    )
    args = parser.parse_args(argv)

    db: Path = args.db
    if not db.is_file():
        print(f"error: database not found: {db}")
        return 1
    db = db.resolve()

    conn = connect(db)
    try:
        before_counts = table_counts(conn)
        schema_before = schema_fingerprint(conn)
        targets = find_portfolios(conn, args.name)

        scope = f'name contains {args.name!r}' if args.name else "ALL portfolios"
        print(f"database : {db}")
        print(f"scope    : {scope}")
        print(f"target   : {len(targets)} portfolio(s) of {before_counts['portfolios']}")
        if targets:
            print()
            for row in targets:
                held = conn.execute(
                    "SELECT COUNT(*) FROM portfolio_holdings WHERE portfolio_id = ?",
                    (row["id"],),
                ).fetchone()[0]
                runs = conn.execute(
                    "SELECT COUNT(*) FROM simulation_runs WHERE portfolio_id = ?",
                    (row["id"],),
                ).fetchone()[0]
                print(
                    f"  id={row['id']:<4} {row['name']:<26} "
                    f"${row['monthly_contribution']:<8} {held} holding(s), {runs} run(s)"
                )

        if args.reset_sequence and args.name:
            print("\nerror: --reset-sequence with --name would leave rows behind")
            return 1

        if not args.apply:
            print("\nDRY RUN - nothing was written. Re-run with --apply to delete.")
            return 0

        if not targets:
            print("\nnothing to delete; database already clean.")
            return 0

        print(f"\nbacking up to {backup(db).name}")
        deleted = 0
        for row in targets:
            if delete_portfolio(conn, row["id"]):
                deleted += 1
        conn.commit()

        if args.reset_sequence:
            remaining = conn.execute("SELECT COUNT(*) FROM portfolios").fetchone()[0]
            if remaining:
                conn.rollback()
                print("error: --reset-sequence needs an empty portfolios table; rolled back")
                return 1
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'portfolios'")
            conn.commit()

        after_counts = table_counts(conn)
        schema_after = schema_fingerprint(conn)

        print(f"deleted  : {deleted} portfolio(s)")
        print("\nrow counts (only owned tables should change):")
        for name, before in before_counts.items():
            after = after_counts[name]
            mark = "  ->" if name in ("portfolios",) + OWNED_TABLES else "    "
            print(f"  {mark} {name:<20} {before:>6} -> {after:<6} {'' if before == after else 'changed'}")

        if schema_after != schema_before:
            conn.rollback()
            print("\nerror: schema changed, rolled back")
            return 1
        print("\nschema unchanged: all CREATE statements identical")
        print("users / tickers / prices / news_sentiment untouched")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
