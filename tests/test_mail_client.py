"""The SMTP client is built before anything is sent and is expected to still work
for the next message, so both boundaries need a stand-in that behaves like a
socket: closing drops it, and writing on a dropped connection fails."""

import smtplib
from email import policy
from email.parser import Parser
from typing import Any, Optional

import pytest

from cloudoll.mail.smtp import Client

CONFIG = {
    "smtp_server": "smtp.example.test",
    "port": 465,
    "account": "sender@example.test",
    "account_name": "发送方",
    "password": "secret",
}


class FakeSMTP:
    connections: list["FakeSMTP"] = []

    def __init__(
        self, host: str, port: int, fail_send: Optional[str] = None, **kw: Any
    ) -> None:
        self.host = host
        self.port = port
        self.debug_level = 0
        self.logins = 0
        self.sent: list[tuple[str, list[str], str]] = []
        self.quit_called = False
        self.closed = False
        self.fail_send = fail_send
        # A live connection holds a socket; close() is what makes it None.
        self.sock: Optional[object] = object()
        FakeSMTP.connections.append(self)

    def set_debuglevel(self, level: int) -> None:
        self.debug_level = level

    def _check(self) -> None:
        if self.sock is None:
            raise smtplib.SMTPServerDisconnected("Connection unexpectedly closed")

    def login(self, user: str, secret: str) -> None:
        self._check()
        self.logins += 1

    def sendmail(self, from_addr: str, to_addrs: list[str], message: str) -> dict:
        self._check()
        if self.fail_send is not None:
            raise smtplib.SMTPException(self.fail_send)
        self.sent.append((from_addr, to_addrs, message))
        return {}

    def quit(self) -> None:
        self.quit_called = True
        self.close()

    def close(self) -> None:
        self.closed = True
        self.sock = None


@pytest.fixture
def connections(monkeypatch):
    FakeSMTP.connections = []
    monkeypatch.setattr("cloudoll.mail.smtp.smtplib.SMTP_SSL", FakeSMTP)
    return FakeSMTP.connections


def _client(**kw: Any) -> Client:
    config = dict(CONFIG, **kw)
    return Client(**config)


def _parts(connection: FakeSMTP) -> list:
    message = Parser(policy=policy.default).parsestr(connection.sent[0][2])
    assert str(message["Subject"]) == "第一封"
    assert "xiaoming@example.test" in message["To"]
    assert message.get_content_type() == "multipart/mixed"
    return list(message.iter_parts())


def test_constructing_a_client_does_not_reach_the_network(connections):
    # Mail settings are read while the process starts up, so a constructor that
    # connected made startup fail outright - or left a session idle until the
    # server closed it and every later send died on the dead socket.
    _client()
    assert connections == []


def test_missing_smtp_server_is_rejected():
    with pytest.raises(ValueError, match="smtp_server"):
        Client(account="sender@example.test", password="secret")


def test_send_without_credentials_names_the_configuration(connections):
    client = Client(smtp_server="smtp.example.test")
    with pytest.raises(KeyError, match="账号密码"):
        client.send()
    # The config defaults are empty strings, so the check has to read falsy.
    assert connections == []


def test_a_blank_recipient_is_rejected(connections):
    with pytest.raises(KeyError, match="邮箱地址"):
        _client().add_to_addr("无名", "")


def test_one_client_can_send_several_messages(connections):
    client = _client()
    client.subject = "第一封"
    client.content = "第一段"
    client.add_to_addr("小明", "xiaoming@example.test")

    client.send()
    client.content = "第二段"
    client.send()

    # send() ends the session, so the next message needs a fresh connection.
    assert [connection.host for connection in connections] == [
        "smtp.example.test",
        "smtp.example.test",
    ]
    assert [connection.logins for connection in connections] == [1, 1]
    for connection, body in zip(connections, ["第一段", "第二段"]):
        # Attaching the body onto the stored message used to make a resent mail
        # carry both bodies.
        assert [
            (part.get_content_type(), part.get_content()) for part in _parts(connection)
        ] == [("text/plain", body)]
        assert connection.sent[0][0] == "sender@example.test"
        assert connection.sent[0][1] == ["xiaoming@example.test"]
        assert connection.quit_called and connection.closed


def test_html_and_attachments_survive_into_the_sent_message(connections, tmp_path):
    attachment = tmp_path / "report.pdf"
    attachment.write_bytes(b"log line")
    client = _client()
    client.subject = "第一封"
    client.content = "正文"
    client.add_to_addr("小明", "xiaoming@example.test")
    client.addfile(attachment)
    client.addhtml("<b>加粗</b>")

    client.send()

    parts = _parts(connections[0])
    assert [part.get_content_type() for part in parts] == [
        "application/pdf",
        "text/html",
        "text/plain",
    ]
    assert parts[0].get_filename() == "report.pdf"
    assert parts[0].get_content_disposition() == "attachment"
    assert parts[0].get_content() == b"log line"
    assert parts[1].get_content() == "<b>加粗</b>"
    assert parts[2].get_content() == "正文"


def test_a_failed_send_still_closes_the_connection(monkeypatch):
    FakeSMTP.connections = []
    monkeypatch.setattr(
        "cloudoll.mail.smtp.smtplib.SMTP_SSL",
        lambda host, port, **kw: FakeSMTP(host, port, fail_send="收件人被服务器拒绝"),
    )
    client = _client()
    client.subject = "第一封"
    client.content = "正文"
    client.add_to_addr("小明", "xiaoming@example.test")
    client.add_to_addr("小红", "xiaohong@example.test")

    with pytest.raises(smtplib.SMTPException, match="收件人被服务器拒绝"):
        client.send()

    assert len(FakeSMTP.connections) == 1
    assert FakeSMTP.connections[0].closed
    assert FakeSMTP.connections[0].sent == []
