"""适老化设置：字体档位、语音播报、高对比度、语音输入开关（阶段 5）。"""
from __future__ import annotations

from app import db

DEFAULT_SETTINGS = {
    "font_level": "large",
    "voice_broadcast": 1,
    "high_contrast": 0,
    "voice_input": 1,
}


def get_settings(conn, user_id: int) -> dict:
    row = conn.execute("SELECT * FROM app_settings WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        return {"user_id": user_id, **DEFAULT_SETTINGS}
    return dict(row)


def update_settings(conn, user_id: int, font_level: str | None = None,
                    voice_broadcast: int | None = None, high_contrast: int | None = None,
                    voice_input: int | None = None) -> dict:
    current = get_settings(conn, user_id)
    now = db.utc_now()
    font_level = current["font_level"] if font_level is None else font_level
    voice_broadcast = current["voice_broadcast"] if voice_broadcast is None else int(voice_broadcast)
    high_contrast = current["high_contrast"] if high_contrast is None else int(high_contrast)
    voice_input = current["voice_input"] if voice_input is None else int(voice_input)

    conn.execute(
        "INSERT INTO app_settings (user_id, font_level, voice_broadcast, high_contrast, voice_input, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET font_level=?, voice_broadcast=?, high_contrast=?, "
        "voice_input=?, updated_at=?",
        (user_id, font_level, voice_broadcast, high_contrast, voice_input, now,
         font_level, voice_broadcast, high_contrast, voice_input, now),
    )
    conn.commit()
    return get_settings(conn, user_id)
