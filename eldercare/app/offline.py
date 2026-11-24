"""客户端本地待同步补偿队列（阶段 2 底座，阶段 6 联调补传）。

模拟手机端断网时的本地队列：录入、标记、留言、求助先落本地，
联网后按本地时间顺序逐条补传；补传成功出队，失败保留重试。
幂等键随载荷保存，服务端凭幂等键去重，避免重复记录。
"""
from __future__ import annotations

import json
import pathlib
import uuid

from app import db


class OfflineQueue:
    def __init__(self, file_path: str | None = None):
        self._file = pathlib.Path(file_path) if file_path else None
        self._items: dict[str, dict] = {}
        self._order: list[str] = []
        if self._file and self._file.exists():
            self._load()

    def add(self, entity_type: str, op: str, payload: dict,
            idempotency_key: str | None = None) -> str:
        key = uuid.uuid4().hex
        item = {
            "key": key,
            "entity_type": entity_type,
            "op": op,
            "payload": payload,
            "idempotency_key": idempotency_key,
            "created_at": db.utc_now(),
            "status": "pending",
            "retries": 0,
        }
        self._items[key] = item
        self._order.append(key)
        self._save()
        return key

    def pending(self) -> list[dict]:
        return [self._items[k] for k in self._order if self._items[k]["status"] == "pending"]

    def mark_done(self, key: str) -> None:
        if key in self._items:
            self._items[key]["status"] = "done"
            self._save()

    def mark_failed(self, key: str) -> None:
        if key in self._items:
            self._items[key]["retries"] += 1
            self._save()

    def __len__(self) -> int:
        return len(self.pending())

    def _save(self) -> None:
        if not self._file:
            return
        self._file.parent.mkdir(parents=True, exist_ok=True)
        self._file.write_text(
            json.dumps(list(self._items.values()), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _load(self) -> None:
        data = json.loads(self._file.read_text(encoding="utf-8"))
        for item in data:
            self._items[item["key"]] = item
            self._order.append(item["key"])
