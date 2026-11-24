"""WebSocket 推送注册表：按用户维护连接，告警/订单变更实时推送给对端。"""
from __future__ import annotations

import json
import sqlite3

from fastapi import WebSocket

from app import bindings


class PushHub:
    def __init__(self) -> None:
        self._conns: dict[int, set[WebSocket]] = {}

    def connect(self, user_id: int, ws: WebSocket) -> None:
        self._conns.setdefault(user_id, set()).add(ws)

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        self._conns.get(user_id, set()).discard(ws)

    async def send(self, user_id: int, payload: dict) -> None:
        dead: list[WebSocket] = []
        for ws in self._conns.get(user_id, set()):
            try:
                await ws.send_text(json.dumps(payload, ensure_ascii=False))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def broadcast_to_families(self, conn: sqlite3.Connection, elder_id: int, payload: dict) -> None:
        """把老人相关变更推送给其全部已绑定家属。"""
        for family_id in bindings.list_family_of_elder(conn, elder_id):
            await self.send(family_id, payload)

    async def broadcast_to_elder(self, elder_id: int, payload: dict) -> None:
        await self.send(elder_id, payload)


hub = PushHub()
