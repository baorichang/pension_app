"""阶段 5 测试：消息、隐私授权、适老化设置与语音占位。"""
import pytest

from app import auth, consents, errors, messages, models, settings, speech


def _user(conn, phone, role):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, role)


def test_message_send_list_and_read(conn):
    elder = _user(conn, "13400000001", models.ROLE_ELDER)
    msg = messages.send_message(conn, elder["user_id"], None, models.MSG_REMINDER, "服药提醒", "该吃降压药了")
    listed = messages.list_messages(conn, elder["user_id"])
    assert len(listed) == 1
    assert listed[0]["read_status"] == "unread"

    read = messages.mark_read(conn, msg["message_id"])
    assert read["read_status"] == "read"
    again = messages.list_messages(conn, elder["user_id"])[0]
    assert again["read_status"] == "read"


def test_message_filter_by_type_and_idempotent(conn):
    elder = _user(conn, "13400000011", models.ROLE_ELDER)
    messages.send_message(conn, elder["user_id"], None, models.MSG_LETTER, "女儿留言", "周末回家",
                          idempotency_key="m-1")
    messages.send_message(conn, elder["user_id"], None, models.MSG_NOTICE, "服务通知", "保洁已预约",
                          idempotency_key="m-1")
    letters = messages.list_messages(conn, elder["user_id"], models.MSG_LETTER)
    assert len(letters) == 1
    assert len(messages.list_messages(conn, elder["user_id"])) == 1


def test_consent_grant_and_revoke(conn):
    elder = _user(conn, "13400000021", models.ROLE_ELDER)
    consents.set_consent(conn, elder["user_id"], elder["user_id"], models.CONSENT_LOCATION, True)
    assert consents.is_granted(conn, elder["user_id"], elder["user_id"], models.CONSENT_LOCATION)

    consents.set_consent(conn, elder["user_id"], elder["user_id"], models.CONSENT_LOCATION, False)
    assert not consents.is_granted(conn, elder["user_id"], elder["user_id"], models.CONSENT_LOCATION)


def test_consent_rejects_unknown_item(conn):
    elder = _user(conn, "13400000031", models.ROLE_ELDER)
    with pytest.raises(errors.ValidationError):
        consents.set_consent(conn, elder["user_id"], elder["user_id"], "camera", True)


def test_settings_default_and_update(conn):
    elder = _user(conn, "13400000041", models.ROLE_ELDER)
    default = settings.get_settings(conn, elder["user_id"])
    assert default["font_level"] == "large"
    assert default["voice_broadcast"] == 1

    updated = settings.update_settings(conn, elder["user_id"], font_level="xlarge", high_contrast=1)
    assert updated["font_level"] == "xlarge"
    assert updated["high_contrast"] == 1
    assert updated["voice_input"] == 1


def test_speech_placeholder_transcribe_and_broadcast(conn):
    assert speech.transcribe("明天上午陪诊") == "明天上午陪诊"
    with pytest.raises(errors.ValidationError):
        speech.transcribe("   ")
    text = speech.build_broadcast_text("服药提醒", "该吃钙片了")
    assert "服药提醒" in text and "钙片" in text
