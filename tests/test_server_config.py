from djlsp.server import DjangoTemplateLanguageServer


def test_server_can_disable_version_check():
    server = DjangoTemplateLanguageServer("django-template-lsp", "1.0.0")
    server.set_initialization_options({"version_check": False})

    assert server.version_check is False


def test_server_applies_plugin_configuration():
    server = DjangoTemplateLanguageServer("django-template-lsp", "1.0.0")
    server.set_initialization_options(
        {
            "plugins": {
                "enabled": ["core-template"],
                "disabled": ["core-template"],
                "hook_timeout_ms": 500,
                "settings": {"core-template": {"example": True}},
            }
        }
    )

    assert "core-template" in server.plugin_manager.disabled_plugins
    assert server.plugin_manager.hook_timeout_ms == 500
    assert server.plugin_manager.settings["core-template"]["example"] is True
