"""
SQLite 数据库管理 — 历史记录 + 源站统计
"""

import sqlite3
import hashlib
import datetime
from config import DB_FILE


class Database:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL,
                normalized_url TEXT NOT NULL UNIQUE,
                title TEXT,
                summary TEXT,
                source_name TEXT,
                source_type TEXT,
                category TEXT,
                sub_category TEXT,
                relevance_score REAL DEFAULT 0,
                fingerprint TEXT,
                is_nju INTEGER DEFAULT 0,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                report_date TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_history_date
                ON history(report_date);
            CREATE INDEX IF NOT EXISTS idx_history_source
                ON history(source_name);
            CREATE INDEX IF NOT EXISTS idx_history_fingerprint
                ON history(fingerprint);
            CREATE INDEX IF NOT EXISTS idx_history_category
                ON history(category);

            CREATE TABLE IF NOT EXISTS source_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_name TEXT NOT NULL UNIQUE,
                url TEXT,
                total_fetches INTEGER DEFAULT 0,
                success_fetches INTEGER DEFAULT 0,
                total_items INTEGER DEFAULT 0,
                last_fetch_at TIMESTAMP,
                last_success_at TIMESTAMP,
                avg_response_ms REAL DEFAULT 0,
                success_rate REAL DEFAULT 1.0
            );

            CREATE TABLE IF NOT EXISTS discovered_sites (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url TEXT NOT NULL UNIQUE,
                title TEXT,
                domain TEXT,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                times_seen INTEGER DEFAULT 1,
                category TEXT,
                is_promoted INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS reports_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_date TEXT UNIQUE NOT NULL,
                file_path TEXT,
                total_items INTEGER DEFAULT 0,
                sources_used INTEGER DEFAULT 0,
                nju_items INTEGER DEFAULT 0,
                github_items INTEGER DEFAULT 0,
                categories TEXT,
                generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)
        self.conn.commit()

    # ── 历史记录 ──────────────────────────────

    def normalize_url(self, url: str) -> str:
        """规范化URL，去掉追踪参数"""
        from urllib.parse import urlparse, urlunparse, parse_qs
        parsed = urlparse(url)
        # 去掉 utm_*, ref, source 等追踪参数
        tracking_params = {"utm_source", "utm_medium", "utm_campaign",
                           "utm_term", "utm_content", "ref", "source",
                           "spm", "from", "scene"}
        query = {k: v for k, v in parse_qs(parsed.query, keep_blank_values=True).items()
                 if k not in tracking_params}
        new_query = "&".join(f"{k}={v[0]}" for k, v in query.items())
        return urlunparse((parsed.scheme, parsed.netloc, parsed.path,
                           parsed.params, new_query, parsed.fragment))

    def is_duplicate(self, url: str = None, fingerprint: str = None) -> bool:
        """检查URL或指纹是否已存在"""
        if url:
            nurl = self.normalize_url(url)
            row = self.conn.execute(
                "SELECT 1 FROM history WHERE normalized_url = ?", (nurl,)
            ).fetchone()
            if row:
                return True
        if fingerprint:
            row = self.conn.execute(
                "SELECT 1 FROM history WHERE fingerprint = ? LIMIT 1", (fingerprint,)
            ).fetchone()
            if row:
                return True
        return False

    def insert_item(self, item: dict) -> bool:
        """插入一条记录，返回是否成功"""
        nurl = self.normalize_url(item.get("url", ""))
        try:
            self.conn.execute("""
                INSERT OR IGNORE INTO history
                    (url, normalized_url, title, summary, source_name, source_type,
                     category, sub_category, relevance_score, fingerprint, is_nju, report_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item.get("url", ""),
                nurl,
                item.get("title", ""),
                item.get("summary", ""),
                item.get("source_name", ""),
                item.get("source_type", ""),
                item.get("category", ""),
                item.get("sub_category", ""),
                item.get("relevance_score", 0),
                item.get("fingerprint", ""),
                item.get("is_nju", 0),
                item.get("report_date", datetime.date.today().isoformat()),
            ))
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_today_count(self) -> int:
        today = datetime.date.today().isoformat()
        row = self.conn.execute(
            "SELECT COUNT(*) as cnt FROM history WHERE report_date = ?", (today,)
        ).fetchone()
        return row["cnt"]

    def get_recent_fingerprints(self, days: int = 7) -> set:
        """获取最近N天的指纹集合用于去重"""
        cutoff = (datetime.date.today() - datetime.timedelta(days=days)).isoformat()
        rows = self.conn.execute(
            "SELECT fingerprint FROM history WHERE report_date >= ? AND fingerprint != ''",
            (cutoff,)
        ).fetchall()
        return {r["fingerprint"] for r in rows}

    # ── 源站统计 ──────────────────────────────

    def update_source_stats(self, source_name: str, url: str,
                            success: bool, elapsed_ms: float = 0,
                            items_count: int = 0):
        now = datetime.datetime.now().isoformat()
        existing = self.conn.execute(
            "SELECT * FROM source_stats WHERE source_name = ?", (source_name,)
        ).fetchone()

        if existing:
            total = existing["total_fetches"] + 1
            success_count = existing["success_fetches"] + (1 if success else 0)
            avg_ms = (existing["avg_response_ms"] * existing["total_fetches"] + elapsed_ms) / total
            self.conn.execute("""
                UPDATE source_stats SET
                    total_fetches = ?, success_fetches = ?,
                    total_items = total_items + ?,
                    last_fetch_at = ?,
                    last_success_at = CASE WHEN ? THEN ? ELSE last_success_at END,
                    avg_response_ms = ?,
                    success_rate = CAST(? AS REAL) / ?
                WHERE source_name = ?
            """, (total, success_count, items_count, now,
                  success, now, avg_ms,
                  success_count, total, source_name))
        else:
            self.conn.execute("""
                INSERT INTO source_stats
                    (source_name, url, total_fetches, success_fetches,
                     total_items, last_fetch_at, last_success_at,
                     avg_response_ms, success_rate)
                VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?)
            """, (source_name, url, 1 if success else 0,
                  items_count, now, now if success else None,
                  elapsed_ms, 1.0 if success else 0.0))
        self.conn.commit()

    def get_source_stats(self) -> list:
        rows = self.conn.execute(
            "SELECT * FROM source_stats ORDER BY success_rate DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ── 发现网站 ──────────────────────────────

    def mark_discovered_site(self, url: str, title: str = "",
                             domain: str = "", category: str = ""):
        from urllib.parse import urlparse
        if not domain and url:
            domain = urlparse(url).netloc
        now = datetime.datetime.now().isoformat()
        existing = self.conn.execute(
            "SELECT * FROM discovered_sites WHERE url = ?", (url,)
        ).fetchone()
        if existing:
            self.conn.execute("""
                UPDATE discovered_sites SET
                    last_seen = ?, times_seen = times_seen + 1,
                    title = CASE WHEN title != '' THEN title ELSE ? END
                WHERE url = ?
            """, (now, existing["title"], url))
        else:
            self.conn.execute("""
                INSERT INTO discovered_sites (url, title, domain, category)
                VALUES (?, ?, ?, ?)
            """, (url, title, domain, category))
        self.conn.commit()

    def get_discovered_sites(self, min_seen: int = 3, limit: int = 50) -> list:
        """获取见过的较多次的陌生网站（可升级为已知源）"""
        rows = self.conn.execute("""
            SELECT * FROM discovered_sites
            WHERE times_seen >= ? AND is_promoted = 0
            ORDER BY times_seen DESC LIMIT ?
        """, (min_seen, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── 报告元数据 ────────────────────────────

    def save_report_meta(self, report_date: str, file_path: str,
                         total_items: int, sources_used: int,
                         nju_items: int = 0, github_items: int = 0,
                         categories: str = ""):
        self.conn.execute("""
            INSERT OR REPLACE INTO reports_meta
                (report_date, file_path, total_items, sources_used,
                 nju_items, github_items, categories)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (report_date, file_path, total_items, sources_used,
              nju_items, github_items, categories))
        self.conn.commit()

    def close(self):
        self.conn.close()


def make_fingerprint(title: str, summary: str = "") -> str:
    """生成内容指纹用于去重"""
    text = (title + " " + summary)[:500]
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()[:16]
