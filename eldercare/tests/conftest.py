"""pytest 公共夹具：每个用例使用独立临时 SQLite 权威库。"""
from __future__ import annotations

import pathlib
import tempfile

import pytest

from app import db


@pytest.fixture()
def conn():
    tmp = pathlib.Path(tempfile.mkdtemp()) / "eldercare_test.db"
    connection = db.connect(str(tmp))
    db.init_db(connection)
    yield connection
    connection.close()
