"""TLS is a server option, so both serving paths have to honour it, and a wrong
certificate setting has to say which key was mis-typed and which file is missing."""

import ssl
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from aiohttp import web

from cloudoll.clitool.watch import start_main_app
from cloudoll.web import Application
from cloudoll.web.configuration import build_ssl_context, validate_config


def write_certificate(root: Path) -> tuple[str, str]:
    """A throwaway localhost certificate; tests never trust it, they hand it over."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(datetime.now(timezone.utc) - timedelta(days=1))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=7))
        .sign(key, hashes.SHA256())
    )
    certfile = root / "cert.pem"
    keyfile = root / "key.pem"
    certfile.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    keyfile.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    return str(certfile), str(keyfile)


def test_certificate_paths_build_a_server_context(tmp_path):
    certfile, keyfile = write_certificate(tmp_path)
    context = build_ssl_context(
        {"ssl_certfile": certfile, "ssl_keyfile": keyfile}, tmp_path
    )
    assert isinstance(context, ssl.SSLContext)


def test_relative_certificate_paths_follow_the_application_root(tmp_path, monkeypatch):
    # A service started from another working directory must still find the files
    # the developer configured, the same rule Configuration.path() applies.
    certfile, keyfile = write_certificate(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    context = build_ssl_context(
        {"ssl_certfile": "cert.pem", "ssl_keyfile": "key.pem"}, tmp_path
    )
    assert isinstance(context, ssl.SSLContext)


def test_a_missing_certificate_file_names_the_key_and_the_path(tmp_path):
    _, keyfile = write_certificate(tmp_path)
    with pytest.raises(ValueError, match="server.ssl_certfile") as error:
        build_ssl_context(
            {"ssl_certfile": "absent.pem", "ssl_keyfile": keyfile}, tmp_path
        )
    message = str(error.value)
    assert "names a missing file" in message
    assert str(tmp_path / "absent.pem") in message
    # The healthy file must not appear: a message that lists both paths leaves
    # the developer guessing which one OpenSSL actually failed to open.
    assert keyfile not in message


def test_a_missing_key_file_names_the_key_and_the_path(tmp_path):
    certfile, _ = write_certificate(tmp_path)
    with pytest.raises(ValueError, match="server.ssl_keyfile") as error:
        build_ssl_context(
            {"ssl_certfile": certfile, "ssl_keyfile": "absent.pem"}, tmp_path
        )
    message = str(error.value)
    assert "names a missing file" in message
    assert str(tmp_path / "absent.pem") in message
    assert certfile not in message


def test_a_key_that_does_not_match_the_certificate_is_explained(tmp_path):
    certfile, _ = write_certificate(tmp_path)
    other = tmp_path / "other"
    other.mkdir()
    _, other_key = write_certificate(other)
    with pytest.raises(ValueError, match="could not be loaded"):
        build_ssl_context(
            {"ssl_certfile": certfile, "ssl_keyfile": other_key}, tmp_path
        )


@pytest.mark.parametrize(
    ("server", "expected"),
    [
        ({"ssl_certfile": "/tmp/cert.pem"}, "set together"),
        ({"ssl_keyfile": "/tmp/key.pem"}, "set together"),
        ({"ssl_certfile": ""}, "must be a non-empty path"),
        ({"ssl_certfile": 42}, "must be a non-empty path"),
        ({"ssl_certfile": "a", "ssl_keyfile": ""}, "must be a non-empty path"),
        ({"ssl_context": "not a context"}, "must be an ssl.SSLContext"),
        ({"ssl_context": 42}, "must be an ssl.SSLContext"),
    ],
)
def test_miswritten_tls_options_are_refused_by_name(server, expected):
    # A bad value has to be reported as the bad value it is, not as a missing
    # companion key: `ssl_certfile: 42` is a type error, not a pairing error.
    with pytest.raises(ValueError, match=expected):
        validate_config({"server": server})


def test_a_context_and_certificate_paths_are_mutually_exclusive():
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    with pytest.raises(ValueError, match="either"):
        build_ssl_context(
            {
                "ssl_context": context,
                "ssl_certfile": "cert.pem",
                "ssl_keyfile": "key.pem",
            },
            Path.cwd(),
        )


def test_application_run_uses_configured_ssl_context(tmp_path, monkeypatch):
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    application = Application(root=tmp_path).create(
        env=None,
        entry_model=None,
        config={"server": {"ssl_context": context}},
    )
    called = {}

    def fake_run_app(app, **options):
        called["app"] = app
        called.update(options)

    monkeypatch.setattr("cloudoll.web.core.web.run_app", fake_run_app)
    application.run()
    assert called["ssl_context"] is context


def test_application_run_builds_the_context_from_certificate_paths(
    tmp_path, monkeypatch
):
    certfile, keyfile = write_certificate(tmp_path)
    application = Application(root=tmp_path).create(
        env=None,
        entry_model=None,
        config={"server": {"ssl_certfile": certfile, "ssl_keyfile": keyfile}},
    )
    called = {}

    def fake_run_app(app, **options):
        called.update(options)

    monkeypatch.setattr("cloudoll.web.core.web.run_app", fake_run_app)
    application.run()
    assert isinstance(called["ssl_context"], ssl.SSLContext)


async def _fetch(url, context):
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(url, ssl=context) as response:
            return response.status, await response.text()


async def _serve(ssl_context):
    application = web.Application()

    async def hello(request):
        return web.Response(text="served")

    application.router.add_get("/", hello)
    runner = web.AppRunner(application)
    await start_main_app(runner, "127.0.0.1", 0, None, ssl_context)
    host, port = next(
        address[:2] for address in runner.addresses if isinstance(address, tuple)
    )
    unverified = ssl._create_unverified_context()
    try:
        scheme = "https" if ssl_context is not None else "http"
        return await _fetch(f"{scheme}://{host}:{port}/", unverified)
    finally:
        await runner.cleanup()


@pytest.fixture
def ready_messages(monkeypatch):
    messages = []
    monkeypatch.setattr(
        "cloudoll.clitool.watch.info",
        lambda message, *args: messages.append(message % args),
    )
    return messages


async def test_the_development_server_serves_https_when_configured(
    ready_messages, tmp_path
):
    certfile, keyfile = write_certificate(tmp_path)
    context = build_ssl_context(
        {"ssl_certfile": certfile, "ssl_keyfile": keyfile}, tmp_path
    )
    status, body = await _serve(context)
    assert (status, body) == (200, "served")
    assert any("https://" in line for line in ready_messages), ready_messages
    assert not any("http://127" in line for line in ready_messages), ready_messages


async def test_the_plain_development_server_still_answers_http(ready_messages):
    status, body = await _serve(None)
    assert (status, body) == (200, "served")
    assert any("http://" in line for line in ready_messages), ready_messages
