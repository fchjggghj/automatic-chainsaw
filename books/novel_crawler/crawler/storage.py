"""
历史记录与存储管理 — SQLite 持久化下载历史、断点续传状态
"""
import sqlite3
import time
import shutil
from pathlib import Path
from dataclasses import dataclass
from typing import Optional


@dataclass
class DownloadRecord:
    id: int = 0
    title: str = ""
    author: str = ""
    url: str = ""
    category: str = ""
    filepath: str = ""
    file_size: int = 0
    checksum: str = ""
    status: str = "pending"  # pending / downloading / completed / failed / verified
    site_name: str = ""
    match_method: str = ""
    match_detail: str = ""
    created_at: str = ""
    completed_at: str = ""


class HistoryDB:
    """下载历史数据库"""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self._conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS downloads (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT DEFAULT '',
                    author TEXT DEFAULT '',
                    url TEXT NOT NULL,
                    category TEXT DEFAULT '',
                    filepath TEXT DEFAULT '',
                    file_size INTEGER DEFAULT 0,
                    checksum TEXT DEFAULT '',
                    status TEXT DEFAULT 'pending',
                    site_name TEXT DEFAULT '',
                    match_method TEXT DEFAULT '',
                    match_detail TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    completed_at TEXT DEFAULT ''
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS search_cache (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keyword TEXT NOT NULL,
                    site TEXT NOT NULL,
                    result_json TEXT,
                    cached_at TEXT DEFAULT (datetime('now','localtime')),
                    UNIQUE(keyword, site)
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS crawl_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT UNIQUE,
                    state_json TEXT,
                    updated_at TEXT DEFAULT (datetime('now','localtime'))
                )
            """)

    def add_record(self, record: DownloadRecord) -> int:
        with self._conn() as c:
            cur = c.execute(
                """INSERT INTO downloads (title, author, url, category, filepath,
                   file_size, checksum, status, site_name, match_method, match_detail)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (record.title, record.author, record.url, record.category,
                 record.filepath, record.file_size, record.checksum, record.status,
                 record.site_name, record.match_method, record.match_detail)
            )
            return cur.lastrowid

    def update_status(self, record_id: int, status: str, filepath: str = "", file_size: int = 0):
        with self._conn() as c:
            if filepath:
                c.execute(
                    "UPDATE downloads SET status=?, filepath=?, file_size=?, completed_at=datetime('now','localtime') WHERE id=?",
                    (status, filepath, file_size, record_id)
                )
            else:
                c.execute("UPDATE downloads SET status=? WHERE id=?", (status, record_id))

    def get_history(self, limit: int = 100, offset: int = 0) -> list[DownloadRecord]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT * FROM downloads ORDER BY id DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return [DownloadRecord(**dict(r)) for r in rows]

    def is_duplicate(self, url: str, checksum: str = "") -> bool:
        with self._conn() as c:
            if checksum:
                r = c.execute("SELECT 1 FROM downloads WHERE checksum=? AND status='completed'", (checksum,)).fetchone()
                if r:
                    return True
            r = c.execute("SELECT 1 FROM downloads WHERE url=? AND status='completed'", (url,)).fetchone()
            return r is not None

    def get_stats(self) -> dict:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM downloads").fetchone()[0]
            completed = c.execute("SELECT COUNT(*) FROM downloads WHERE status='completed'").fetchone()[0]
            by_method = dict(c.execute(
                "SELECT match_method, COUNT(*) FROM downloads WHERE match_method!='' GROUP BY match_method"
            ).fetchall())
        return {"total": total, "completed": completed, "by_method": by_method}

    def cache_search(self, keyword: str, site: str, results_json: str):
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO search_cache (keyword, site, result_json, cached_at) VALUES (?,?,?,datetime('now','localtime'))",
                (keyword, site, results_json)
            )

    def get_search_cache(self, keyword: str, site: str, max_age_sec: int = 3600) -> Optional[str]:
        with self._conn() as c:
            r = c.execute(
                "SELECT result_json FROM search_cache WHERE keyword=? AND site=? AND datetime(cached_at) > datetime('now','localtime',?)",
                (keyword, site, f"-{max_age_sec} seconds")
            ).fetchone()
        return r[0] if r else None

    def save_crawl_state(self, task_id: str, state_json: str):
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO crawl_state (task_id, state_json, updated_at) VALUES (?,?,datetime('now','localtime'))",
                (task_id, state_json)
            )

    def get_crawl_state(self, task_id: str) -> Optional[str]:
        with self._conn() as c:
            r = c.execute("SELECT state_json FROM crawl_state WHERE task_id=?", (task_id,)).fetchone()
        return r[0] if r else None


class StorageManager:
    """文件存储管理器 — 按类型/作者/来源自动归档"""

    def __init__(self, base_dir: Path, organize_by: str = "category"):
        self.base_dir = Path(base_dir)
        self.organize_by = organize_by

    def get_target_dir(self, category: str = "", author: str = "", site: str = "") -> Path:
        if self.organize_by == "category" and category:
            d = self.base_dir / category
        elif self.organize_by == "author" and author:
            d = self.base_dir / author
        elif self.organize_by == "site" and site:
            d = self.base_dir / site
        else:
            d = self.base_dir / "unsorted"
        d.mkdir(parents=True, exist_ok=True)
        return d

    def organize(self, filepath: Path, category: str = "", author: str = "", site: str = "") -> Path:
        target_dir = self.get_target_dir(category, author, site)
        target = target_dir / filepath.name
        if target.exists():
            target = target_dir / f"{filepath.stem}_dup_{int(time.time())}{filepath.suffix}"
        shutil.move(str(filepath), str(target))
        return target
