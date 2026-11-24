"""业务异常与统一响应结构。

接口统一返回：{"code", "message", "data", "serverTime"}
"""
from __future__ import annotations

import datetime as _dt


def _server_time() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class AppError(Exception):
    """基础业务异常。"""

    code = 500

    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class NotFoundError(AppError):
    code = 404


class PermissionError(AppError):
    code = 403


class ValidationError(AppError):
    code = 400


class ConflictError(AppError):
    code = 409


def ok(data=None, message: str = "ok") -> dict:
    return {"code": 0, "message": message, "data": data, "serverTime": _server_time()}


def fail(exc: AppError) -> dict:
    return {"code": exc.code, "message": exc.message, "data": None, "serverTime": _server_time()}
