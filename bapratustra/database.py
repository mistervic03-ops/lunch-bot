"""Small SQLite store for the opt-in candidate management alpha."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from bapratustra.recommendation import LunchOption, normalize_name
from bapratustra.sheets import RecommendationLogEntry


SCHEMA_VERSION = 1


class CandidateValidationError(ValueError):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__("candidate validation failed")
        self.errors = errors


class DuplicateCandidateError(ValueError):
    def __init__(self, existing_id: int) -> None:
        super().__init__("restaurant and menu already exist")
        self.existing_id = existing_id


@dataclass(frozen=True)
class CandidateInput:
    restaurant: str
    menu: str
    price: int | None = None
    map_url: str | None = None
    recommended_by: str | None = None
    note: str | None = None


@dataclass(frozen=True)
class StoredCandidate:
    id: int
    active: bool
    restaurant: str
    menu: str
    price: int | None
    map_url: str | None
    recommended_by: str | None
    note: str | None
    created_at: str
    updated_at: str

    def to_lunch_option(self) -> LunchOption:
        return LunchOption(
            restaurant=self.restaurant,
            menu=self.menu,
            price=self.price,
            map_url=self.map_url,
            recommended_by=self.recommended_by,
            note=self.note,
        )


@dataclass(frozen=True)
class CandidateChange:
    id: int
    candidate_id: int
    action: str
    actor: str | None
    before: dict[str, Any] | None
    after: dict[str, Any]
    created_at: str


def validate_candidate(values: dict[str, str]) -> CandidateInput:
    restaurant = normalize_name(values.get("restaurant", ""))
    menu = normalize_name(values.get("menu", ""))
    errors: dict[str, str] = {}
    if not restaurant:
        errors["restaurant"] = "식당 이름을 입력해주세요."
    if not menu:
        errors["menu"] = "추천 메뉴를 입력해주세요."

    price_text = values.get("price", "").strip().replace(",", "")
    price: int | None = None
    if price_text:
        if not price_text.isdigit():
            errors["price"] = "가격은 0 이상의 숫자로 입력해주세요."
        else:
            price = int(price_text)

    map_url = values.get("map_url", "").strip() or None
    if map_url:
        parsed = urlparse(map_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            errors["map_url"] = "http 또는 https로 시작하는 링크를 입력해주세요."

    if errors:
        raise CandidateValidationError(errors)
    return CandidateInput(
        restaurant=restaurant,
        menu=menu,
        price=price,
        map_url=map_url,
        recommended_by=normalize_name(values.get("recommended_by", "")) or None,
        note=values.get("note", "").strip() or None,
    )


def _key(value: str) -> str:
    return normalize_name(value).casefold()


def _timestamp(now: datetime | None = None) -> str:
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("now must include timezone information")
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


class CandidateDatabase:
    def __init__(self, path: Path) -> None:
        self.path = path

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    id INTEGER PRIMARY KEY,
                    active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
                    restaurant TEXT NOT NULL,
                    menu TEXT NOT NULL,
                    restaurant_key TEXT NOT NULL,
                    menu_key TEXT NOT NULL,
                    price INTEGER CHECK (price IS NULL OR price >= 0),
                    map_url TEXT,
                    recommended_by TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (restaurant_key, menu_key)
                );
                CREATE INDEX IF NOT EXISTS candidates_active_name_idx
                    ON candidates (active, restaurant_key, menu_key);

                CREATE TABLE IF NOT EXISTS recommendation_log (
                    id INTEGER PRIMARY KEY,
                    recommended_at TEXT NOT NULL,
                    run_date_kst TEXT NOT NULL,
                    position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 3),
                    restaurant TEXT NOT NULL,
                    menu TEXT NOT NULL,
                    slack_channel_id TEXT NOT NULL,
                    slack_message_ts TEXT NOT NULL,
                    like_count INTEGER NOT NULL DEFAULT 0 CHECK (like_count >= 0),
                    likes_synced_at TEXT,
                    UNIQUE (slack_channel_id, slack_message_ts, position)
                );

                CREATE TABLE IF NOT EXISTS candidate_changes (
                    id INTEGER PRIMARY KEY,
                    candidate_id INTEGER NOT NULL REFERENCES candidates(id),
                    action TEXT NOT NULL,
                    actor TEXT,
                    before_json TEXT,
                    after_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS candidate_changes_recent_idx
                    ON candidate_changes (created_at DESC, id DESC);
                """
            )
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in {0, SCHEMA_VERSION}:
                raise RuntimeError(f"unsupported database schema version: {version}")
            connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def is_empty(self) -> bool:
        with self.connect() as connection:
            candidate_count = connection.execute(
                "SELECT COUNT(*) FROM candidates"
            ).fetchone()[0]
            log_count = connection.execute(
                "SELECT COUNT(*) FROM recommendation_log"
            ).fetchone()[0]
        return candidate_count == 0 and log_count == 0

    def get_candidate(self, candidate_id: int) -> StoredCandidate | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
            ).fetchone()
        return _candidate_from_row(row) if row else None

    def find_duplicate(self, candidate: CandidateInput) -> StoredCandidate | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM candidates
                WHERE restaurant_key = ? AND menu_key = ?
                """,
                (_key(candidate.restaurant), _key(candidate.menu)),
            ).fetchone()
        return _candidate_from_row(row) if row else None

    def list_candidates(
        self, *, search: str = "", include_inactive: bool = True
    ) -> tuple[StoredCandidate, ...]:
        clauses: list[str] = []
        parameters: list[object] = []
        if not include_inactive:
            clauses.append("active = 1")
        normalized_search = normalize_name(search).casefold()
        if normalized_search:
            clauses.append("(restaurant_key LIKE ? OR menu_key LIKE ?)")
            pattern = f"%{normalized_search}%"
            parameters.extend((pattern, pattern))
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with self.connect() as connection:
            rows = connection.execute(
                "SELECT * FROM candidates"
                + where
                + " ORDER BY active DESC, restaurant_key, menu_key",
                parameters,
            ).fetchall()
        return tuple(_candidate_from_row(row) for row in rows)

    def create_candidate(
        self,
        candidate: CandidateInput,
        *,
        actor: str | None = None,
        now: datetime | None = None,
    ) -> StoredCandidate:
        timestamp = _timestamp(now)
        try:
            with self.connect() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO candidates (
                        active, restaurant, menu, restaurant_key, menu_key,
                        price, map_url, recommended_by, note, created_at, updated_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        candidate.restaurant,
                        candidate.menu,
                        _key(candidate.restaurant),
                        _key(candidate.menu),
                        candidate.price,
                        candidate.map_url,
                        candidate.recommended_by,
                        candidate.note,
                        timestamp,
                        timestamp,
                    ),
                )
                stored = self._get_candidate(connection, cursor.lastrowid)
                self._record_change(
                    connection, stored.id, "create", actor, None, stored, timestamp
                )
        except sqlite3.IntegrityError as exc:
            duplicate = self.find_duplicate(candidate)
            if duplicate:
                raise DuplicateCandidateError(duplicate.id) from exc
            raise
        return stored

    def update_candidate(
        self,
        candidate_id: int,
        candidate: CandidateInput,
        *,
        actor: str | None = None,
        now: datetime | None = None,
    ) -> StoredCandidate:
        timestamp = _timestamp(now)
        try:
            with self.connect() as connection:
                before = self._get_candidate(connection, candidate_id)
                connection.execute(
                    """
                    UPDATE candidates SET
                        restaurant = ?, menu = ?, restaurant_key = ?, menu_key = ?,
                        price = ?, map_url = ?, recommended_by = ?, note = ?,
                        updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        candidate.restaurant,
                        candidate.menu,
                        _key(candidate.restaurant),
                        _key(candidate.menu),
                        candidate.price,
                        candidate.map_url,
                        candidate.recommended_by,
                        candidate.note,
                        timestamp,
                        candidate_id,
                    ),
                )
                after = self._get_candidate(connection, candidate_id)
                self._record_change(
                    connection, candidate_id, "update", actor, before, after, timestamp
                )
        except sqlite3.IntegrityError as exc:
            duplicate = self.find_duplicate(candidate)
            if duplicate:
                raise DuplicateCandidateError(duplicate.id) from exc
            raise
        return after

    def set_active(
        self,
        candidate_id: int,
        active: bool,
        *,
        actor: str | None = None,
        now: datetime | None = None,
    ) -> StoredCandidate:
        timestamp = _timestamp(now)
        with self.connect() as connection:
            before = self._get_candidate(connection, candidate_id)
            connection.execute(
                "UPDATE candidates SET active = ?, updated_at = ? WHERE id = ?",
                (int(active), timestamp, candidate_id),
            )
            after = self._get_candidate(connection, candidate_id)
            action = "reactivate" if active else "deactivate"
            self._record_change(
                connection, candidate_id, action, actor, before, after, timestamp
            )
        return after

    def recent_changes(self, *, limit: int = 30) -> tuple[CandidateChange, ...]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM candidate_changes
                ORDER BY id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return tuple(
            CandidateChange(
                id=row["id"],
                candidate_id=row["candidate_id"],
                action=row["action"],
                actor=row["actor"],
                before=json.loads(row["before_json"]) if row["before_json"] else None,
                after=json.loads(row["after_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        )

    def import_snapshot(
        self,
        candidates: Sequence[tuple[bool, LunchOption]],
        entries: Sequence[RecommendationLogEntry],
        *,
        now: datetime | None = None,
    ) -> None:
        if not self.is_empty():
            raise RuntimeError("alpha database must be empty before import")
        timestamp = _timestamp(now)
        with self.connect() as connection:
            for active, option in candidates:
                cursor = connection.execute(
                    """
                    INSERT INTO candidates (
                        active, restaurant, menu, restaurant_key, menu_key,
                        price, map_url, recommended_by, note, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(active), option.restaurant, option.menu,
                        _key(option.restaurant), _key(option.menu), option.price,
                        option.map_url, option.recommended_by, option.note,
                        timestamp, timestamp,
                    ),
                )
                stored = self._get_candidate(connection, cursor.lastrowid)
                self._record_change(
                    connection, stored.id, "import", None, None, stored, timestamp
                )
            for entry in entries:
                connection.execute(
                    """
                    INSERT INTO recommendation_log (
                        recommended_at, run_date_kst, position, restaurant, menu,
                        slack_channel_id, slack_message_ts, like_count,
                        likes_synced_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        entry.recommended_at.isoformat(),
                        entry.run_date_kst.isoformat(),
                        entry.position,
                        entry.restaurant,
                        entry.menu,
                        entry.slack_channel_id,
                        entry.slack_message_ts,
                        entry.like_count,
                        entry.likes_synced_at.isoformat()
                        if entry.likes_synced_at else None,
                    ),
                )

    def counts(self) -> tuple[int, int]:
        with self.connect() as connection:
            candidates = connection.execute(
                "SELECT COUNT(*) FROM candidates"
            ).fetchone()[0]
            logs = connection.execute(
                "SELECT COUNT(*) FROM recommendation_log"
            ).fetchone()[0]
        return candidates, logs

    def backup(self, directory: Path, *, now: datetime | None = None) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        timestamp = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        target = directory / f"bapratustra-{timestamp:%Y%m%dT%H%M%S%fZ}.sqlite3"
        with self.connect() as source, sqlite3.connect(target) as destination:
            source.backup(destination)
        with sqlite3.connect(target) as check:
            result = check.execute("PRAGMA integrity_check").fetchone()[0]
        if result != "ok":
            raise RuntimeError(f"backup integrity check failed: {result}")
        return target

    def prune_backups(self, directory: Path, *, keep: int = 30) -> tuple[Path, ...]:
        if keep < 1:
            raise ValueError("keep must be at least 1")
        backups = sorted(directory.glob("bapratustra-*.sqlite3"), reverse=True)
        removed: list[Path] = []
        for backup in backups[keep:]:
            if backup.is_file():
                backup.unlink()
                removed.append(backup)
        return tuple(removed)

    def _get_candidate(
        self, connection: sqlite3.Connection, candidate_id: int
    ) -> StoredCandidate:
        row = connection.execute(
            "SELECT * FROM candidates WHERE id = ?", (candidate_id,)
        ).fetchone()
        if row is None:
            raise KeyError(candidate_id)
        return _candidate_from_row(row)

    def _record_change(
        self,
        connection: sqlite3.Connection,
        candidate_id: int,
        action: str,
        actor: str | None,
        before: StoredCandidate | None,
        after: StoredCandidate,
        timestamp: str,
    ) -> None:
        connection.execute(
            """
            INSERT INTO candidate_changes (
                candidate_id, action, actor, before_json, after_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                candidate_id,
                action,
                normalize_name(actor or "") or None,
                json.dumps(asdict(before), ensure_ascii=False) if before else None,
                json.dumps(asdict(after), ensure_ascii=False),
                timestamp,
            ),
        )


def _candidate_from_row(row: sqlite3.Row) -> StoredCandidate:
    return StoredCandidate(
        id=row["id"],
        active=bool(row["active"]),
        restaurant=row["restaurant"],
        menu=row["menu"],
        price=row["price"],
        map_url=row["map_url"],
        recommended_by=row["recommended_by"],
        note=row["note"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
