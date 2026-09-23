-- Schema for the AI-Powered ETF & Index Investing Simulator
-- Applied automatically on app startup (see app/database.py) if the DB is empty.
-- Simpler than alembic for an MVP; revisit if we need forward/backward migrations.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tickers (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol   TEXT    NOT NULL UNIQUE,
    name     TEXT,
    sector   TEXT
);

CREATE TABLE IF NOT EXISTS prices (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id  INTEGER NOT NULL REFERENCES tickers(id),
    date       TEXT    NOT NULL,                  -- ISO date (YYYY-MM-DD)
    close      REAL    NOT NULL,
    volume     INTEGER,
    UNIQUE (ticker_id, date)
);

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    created_at TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolios (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id              INTEGER NOT NULL REFERENCES users(id),
    name                 TEXT    NOT NULL,
    monthly_contribution REAL    NOT NULL DEFAULT 0,
    start_date           TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_holdings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id  INTEGER NOT NULL REFERENCES portfolios(id),
    ticker_id     INTEGER NOT NULL REFERENCES tickers(id),
    weight        REAL    NOT NULL CHECK (weight >= 0)
);

CREATE TABLE IF NOT EXISTS simulation_runs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES portfolios(id),
    params_json TEXT    NOT NULL,
    stats_json  TEXT,                             -- distribution summary (nullable for legacy runs)
    created_at  TEXT    NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS simulation_results (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id     INTEGER NOT NULL REFERENCES simulation_runs(id),
    percentile REAL    NOT NULL,                  -- e.g. 10, 50, 90
    path_json  TEXT    NOT NULL                   -- serialized trajectory
);

CREATE TABLE IF NOT EXISTS news_sentiment (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker_id_or_null INTEGER REFERENCES tickers(id),  -- null for macro/geopolitical
    headline          TEXT    NOT NULL,
    source            TEXT,
    published_at      TEXT,
    sentiment_score   REAL,                            -- -1..1
    category          TEXT    NOT NULL CHECK (category IN ('sector', 'geopolitical'))
);

CREATE INDEX IF NOT EXISTS idx_prices_ticker_date        ON prices (ticker_id, date);
CREATE INDEX IF NOT EXISTS idx_portfolio_holdings_port   ON portfolio_holdings (portfolio_id);
CREATE INDEX IF NOT EXISTS idx_sim_runs_portfolio        ON simulation_runs (portfolio_id);
CREATE INDEX IF NOT EXISTS idx_sim_results_run           ON simulation_results (run_id);
CREATE INDEX IF NOT EXISTS idx_news_ticker_published     ON news_sentiment (ticker_id_or_null, published_at);
CREATE INDEX IF NOT EXISTS idx_news_category_published
    ON news_sentiment (category, published_at);