"""FastAPI 应用组装：路由、异常处理、静态演示页与 WebSocket 推送。"""
from __future__ import annotations

import pathlib

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app import errors
from app.web import deps, routes
from app.web.push import hub

STATIC_DIR = pathlib.Path(__file__).resolve().parent / "static"

app = FastAPI(title="养老 App 后端演示", version="1.0.0")


@app.on_event("startup")
def _startup() -> None:
    deps.init_server_db()


@app.exception_handler(errors.AppError)
def _app_error(_: Request, exc: errors.AppError):
    return JSONResponse(status_code=exc.code, content=errors.fail(exc))


app.include_router(routes.router)


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket, user_id: int):
    await ws.accept()
    hub.connect(user_id, ws)
    try:
        while True:
            await ws.receive_text()  # 接收心跳；首版不处理下行消息
    except WebSocketDisconnect:
        hub.disconnect(user_id, ws)


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
