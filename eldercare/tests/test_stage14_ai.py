"""阶段 14：在线大模型对接与本地兜底。"""
from __future__ import annotations

import pathlib

from app import ai

HTML = pathlib.Path(__file__).resolve().parent.parent / "app" / "web" / "static" / "index.html"


def test_not_configured_without_key(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    assert ai.is_configured() is False


def test_local_reply_keywords():
    assert "健康" in ai.local_reply("血压怎么量")
    assert "用药" in ai.local_reply("忘记吃药了")
    assert "SOS" in ai.local_reply("我摔倒了需要帮助")
    assert "服务" in ai.local_reply("想预约上门助浴")
    assert "您好" in ai.local_reply("你好")


def test_chat_falls_back_to_local_without_key(monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    result = ai.chat("血压偏高要注意什么")
    assert result["source"] == "local"
    assert result["reply"]


def test_chat_empty_message():
    result = ai.chat("   ")
    assert result["source"] == "local"
    assert result["reply"]


def test_frontend_calls_backend_ai_endpoint():
    html = HTML.read_text(encoding="utf-8")
    for token in ("/api/ai/chat", "正在输入…", "sendAi", "history"):
        assert token in html, f"前端 AI 对接缺少要素 {token}"
