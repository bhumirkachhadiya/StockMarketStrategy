"""
Database Service & Persistent Storage
Supports local SQLite and production PostgreSQL (Supabase / Neon / Render)
via DATABASE_URL environment variable.
"""
import os
import sqlite3
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime

logger = logging.getLogger("Database")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "platform.db")

class Database:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Database, cls).__new__(cls)
            cls._instance._init_db()
        return cls._instance

    def _init_db(self):
        os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
        self.db_url = os.environ.get("DATABASE_URL")
        self.is_postgres = bool(self.db_url and self.db_url.startswith("postgres"))

        if not self.is_postgres:
            self._init_sqlite()
        else:
            logger.info("Using PostgreSQL database connection.")

    def _get_connection(self):
        if self.is_postgres:
            import psycopg2
            return psycopg2.connect(self.db_url)
        else:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            return conn

    def _init_sqlite(self):
        conn = self._get_connection()
        cur = conn.cursor()

        # Users configuration table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_id TEXT UNIQUE,
                api_key TEXT,
                pin TEXT,
                totp_secret TEXT,
                updated_at TEXT
            )
        """)

        # Platform settings table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TEXT
            )
        """)

        # Strategy signals history table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS strategy_signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                symbol TEXT,
                direction TEXT,
                option_type TEXT,
                strike REAL,
                ltp REAL,
                entry REAL,
                stop_loss REAL,
                target_1 REAL,
                target_2 REAL,
                status TEXT
            )
        """)

        conn.commit()
        conn.close()

    def get_setting(self, key: str, default: Any = None) -> Any:
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("SELECT value FROM platform_settings WHERE key = ?", (key,))
            row = cur.fetchone()
            conn.close()
            if row:
                return json.loads(row["value"])
        except Exception as e:
            logger.warning(f"Error reading setting {key}: {e}")
        return default

    def set_setting(self, key: str, value: Any):
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            val_str = json.dumps(value)
            now = datetime.now().isoformat()
            cur.execute("""
                INSERT INTO platform_settings (key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
            """, (key, val_str, now))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Error saving setting {key}: {e}")

    def log_signal(self, signal: Dict[str, Any]):
        try:
            conn = self._get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO strategy_signals (
                    timestamp, symbol, direction, option_type, strike,
                    ltp, entry, stop_loss, target_1, target_2, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                datetime.now().isoformat(),
                signal.get("symbol"),
                signal.get("direction"),
                signal.get("option_type"),
                signal.get("strike", 0.0),
                signal.get("underlying_ltp", 0.0),
                signal.get("entry", 0.0),
                signal.get("stop_loss", 0.0),
                signal.get("target_1", 0.0),
                signal.get("target_2", 0.0),
                signal.get("status", "")
            ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.warning(f"Error logging signal: {e}")
