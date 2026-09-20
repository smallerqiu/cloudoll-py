from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from cloudoll.clitool.process import ProcessManager
from cloudoll.orm.parse import parse_sql, to_list


@pytest.mark.parametrize(
    "arguments,expected",
    [
        (["cloudoll", "start", "--name", "api"], True),
        (["cloudoll", "start", "-n", "api"], True),
        (["cloudoll", "start", "--name=api"], True),
        (["cloudoll", "start", "--name", "api-other"], False),
        (["cloudoll", "start", "--name", "other"], False),
        (["cloudoll", "start", "--name"], False),
    ],
)
def test_process_checks_target_pid_and_exact_name(
    monkeypatch, tmp_path, arguments, expected
):
    import json

    monkeypatch.setattr(ProcessManager, "get_run_dir", lambda: tmp_path)
    (tmp_path / "api.pid").write_text(
        json.dumps({"pid": 12345, "created": 123.0, "cmdline": arguments})
    )
    process = Mock(
        cmdline=Mock(return_value=arguments),
        is_running=Mock(return_value=True),
        status=Mock(return_value="running"),
        create_time=Mock(return_value=123.0),
    )
    factory = Mock(return_value=process)
    monkeypatch.setattr("cloudoll.clitool.process.psutil.Process", factory)
    assert ProcessManager._valid_process(12345, "api") is expected
    factory.assert_called_once_with(12345)


def test_url_query_preserves_bytes_and_blank_values():
    assert parse_sql("a=1&a=2&b=", keep_blank_values=True) == [
        ("a", "1"),
        ("a", "2"),
        ("b", ""),
    ]
    assert parse_sql(b"a=1") == [(b"a", b"1")]
    assert to_list(None) == []


def test_missing_jwt_key_never_accepts_unsigned_configuration():
    from cloudoll.web import Application

    application = Application()
    assert application.jwt_decode("irrelevant") is None


async def test_upload_uses_server_generated_path(tmp_path, monkeypatch):
    from unittest.mock import AsyncMock

    from cloudoll.template.controllers.upload.upload import upload

    monkeypatch.chdir(tmp_path)
    file = SimpleNamespace(
        filename="../../outside.txt", read=AsyncMock(return_value=b"data")
    )
    # Access the original endpoint without entering an HTTP/session pipeline.
    result = await upload.fn.handler(None, file)
    saved = tmp_path / "static" / "upload" / result["file_name"]
    assert saved.read_bytes() == b"data"
    assert saved.parent == tmp_path / "static" / "upload"
    assert result["file_name"] != file.filename
    assert not (tmp_path / "outside.txt").exists()
