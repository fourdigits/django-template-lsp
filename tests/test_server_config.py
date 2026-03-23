from djlsp.server import DjangoTemplateLanguageServer


def test_server_can_disable_version_check():
    server = DjangoTemplateLanguageServer("django-template-lsp", "1.0.0")
    server.set_initialization_options({"version_check": False})

    assert server.version_check is False
