"""阶段 1 测试：认证登录、亲属绑定与访问权限。"""
import pytest

from app import auth, bindings, errors, models


def _elder(conn, phone="13900000001"):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_ELDER)


def _family(conn, phone="13900000002"):
    return auth.login(conn, phone, auth.DEV_FIXED_CODE, models.ROLE_FAMILY)


def test_login_creates_user_with_token_and_role(conn):
    res = _elder(conn)
    assert res["user_id"] > 0
    assert res["role"] == models.ROLE_ELDER
    assert res["token"]

    user = auth.get_user_by_token(conn, res["token"])
    assert user is not None
    assert user["phone"] == "13900000001"


def test_wrong_code_rejected(conn):
    with pytest.raises(errors.ValidationError):
        auth.login(conn, "13900000003", "999999", models.ROLE_ELDER)


def test_phone_cannot_switch_role(conn):
    _elder(conn, "13900000004")
    with pytest.raises(errors.ValidationError):
        auth.login(conn, "13900000004", auth.DEV_FIXED_CODE, models.ROLE_FAMILY)


def test_bind_one_elder_multiple_families_and_vice_versa(conn):
    elder = _elder(conn)
    f1 = _family(conn, "13900000011")
    f2 = _family(conn, "13900000012")
    elder2 = _elder(conn, "13900000013")

    bindings.bind(conn, elder["user_id"], f1["user_id"])
    bindings.bind(conn, elder["user_id"], f2["user_id"])
    bindings.bind(conn, elder2["user_id"], f1["user_id"])

    assert set(bindings.list_family_of_elder(conn, elder["user_id"])) == {f1["user_id"], f2["user_id"]}
    assert set(bindings.list_elders_of_family(conn, f1["user_id"])) == {elder["user_id"], elder2["user_id"]}


def test_bind_is_idempotent(conn):
    elder = _elder(conn)
    family = _family(conn)
    first = bindings.bind(conn, elder["user_id"], family["user_id"])
    second = bindings.bind(conn, elder["user_id"], family["user_id"])
    assert first["relation_id"] == second["relation_id"]
    rows = conn.execute(
        "SELECT COUNT(*) AS c FROM family_relations WHERE elder_id=? AND family_id=?",
        (elder["user_id"], family["user_id"]),
    ).fetchone()
    assert rows["c"] == 1


def test_unbind_revokes_access(conn):
    elder = _elder(conn)
    family = _family(conn)
    bindings.bind(conn, elder["user_id"], family["user_id"])
    assert bindings.can_access(conn, family["user_id"], elder["user_id"])

    bindings.unbind(conn, elder["user_id"], family["user_id"])
    assert not bindings.can_access(conn, family["user_id"], elder["user_id"])
    assert bindings.list_elders_of_family(conn, family["user_id"]) == []


def test_access_without_bind_raises_permission(conn):
    elder = _elder(conn)
    family = _family(conn)
    with pytest.raises(errors.PermissionError):
        bindings.assert_can_access(conn, family["user_id"], elder["user_id"])


def test_bind_rejects_wrong_role(conn):
    elder = _elder(conn)
    other_elder = _elder(conn, "13900000021")
    with pytest.raises(errors.ValidationError):
        bindings.bind(conn, elder["user_id"], other_elder["user_id"])
