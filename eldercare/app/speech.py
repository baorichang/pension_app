"""语音能力占位（阶段 5）。

首版不接真实语音识别/合成服务：transcribe 为语音转文字占位，
播报由客户端 TTS 完成。未授权麦克风时上层应回退纯文字输入。
"""
from __future__ import annotations

from app import errors


def transcribe(audio_ref: str) -> str:
    """将语音输入转写为文字（占位实现）。

    真实环境替换为语音识别服务；当前直接返回传入的文本占位，便于流程联调。
    """
    if not audio_ref or not str(audio_ref).strip():
        raise errors.ValidationError("语音内容为空")
    return str(audio_ref).strip()


def build_broadcast_text(title: str, body: str = "") -> str:
    """组装供 TTS 播报的文本（待办/告警/订单状态等关键信息）。"""
    return f"{title}。{body}".strip("。 ")
