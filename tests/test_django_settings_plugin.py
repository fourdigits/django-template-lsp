import jedi
from lsprotocol.types import DiagnosticSeverity
from pygls.workspace import TextDocument

from djlsp.index import WorkspaceIndex
from djlsp.plugins import DjangoSettingsPlugin, PluginContext


def create_context(*, source: str, uri: str) -> PluginContext:
    return PluginContext(
        workspace_index=WorkspaceIndex(),
        jedi_project=jedi.Project("."),
        document=TextDocument(uri=uri, source=source),
    )


def create_plugin() -> DjangoSettingsPlugin:
    return DjangoSettingsPlugin(
        settings_keys_provider=lambda _context: {"DEBUG", "ALLOWED_HOSTS", "SECRET_KEY"}
    )


def test_settings_plugin_template_completions():
    context = create_context(
        source="{{ settings.D",
        uri="file:///project/templates/base.html",
    )

    items = create_plugin().on_completions(context, line=0, character=13)

    assert [item.label for item in items] == ["DEBUG"]


def test_settings_plugin_python_completions():
    context = create_context(
        source="settings.AL",
        uri="file:///project/views.py",
    )

    items = create_plugin().on_completions(context, line=0, character=11)

    assert [item.label for item in items] == ["ALLOWED_HOSTS"]


def test_settings_plugin_reports_unknown_keys():
    context = create_context(
        source=(
            "{{ settings.NOT_A_KEY }}\n"
            "value = settings.DEBUG\n"
            "print(settings.NOPE)\n"
        ),
        uri="file:///project/templates/base.html",
    )

    diagnostics = create_plugin().on_diagnostics(context)
    messages = [item.message for item in diagnostics]

    assert "Unknown Django setting key: 'NOT_A_KEY'" in messages
    assert "Unknown Django setting key: 'NOPE'" in messages
    assert all(item.severity == DiagnosticSeverity.Warning for item in diagnostics)
    assert all(item.source == "django-settings" for item in diagnostics)


def test_settings_plugin_skips_non_template_and_non_python_files():
    context = create_context(
        source="settings.NOPE",
        uri="file:///project/static/app.js",
    )

    diagnostics = create_plugin().on_diagnostics(context)

    assert diagnostics == []
