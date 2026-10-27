import ssl

from cloudoll.web import Application


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
