import jedi
from lsprotocol.types import DiagnosticSeverity
from pygls.workspace import TextDocument

from djlsp.index import WorkspaceIndex
from djlsp.plugins import DjangoUrlsPlugin, PluginContext


def create_context(*, source: str, uri: str) -> PluginContext:
    index = WorkspaceIndex()
    index.update(
        {
            "urls": {
                "app:index": {"docs": "Index url", "source": "src:urls.py:1"},
                "app:detail": {"docs": "Detail url", "source": "src:urls.py:2"},
            }
        }
    )
    return PluginContext(
        workspace_index=index,
        jedi_project=jedi.Project("."),
        document=TextDocument(uri=uri, source=source),
    )


def test_django_urls_plugin_completes_template_url_names():
    context = create_context(
        source="{% url 'app:i",
        uri="file:///project/templates/base.html",
    )

    items = DjangoUrlsPlugin().on_completions(context, line=0, character=13)

    assert [item.label for item in items] == ["app:index"]


def test_django_urls_plugin_completes_python_reverse_names():
    context = create_context(
        source="reverse('app:d",
        uri="file:///project/views.py",
    )

    items = DjangoUrlsPlugin().on_completions(context, line=0, character=14)

    assert [item.label for item in items] == ["app:detail"]


def test_django_urls_plugin_reports_unknown_template_and_python_urls():
    context = create_context(
        source=(
            "{% url 'app:missing' %}\n"
            "reverse('app:detail')\n"
            "redirect('app:unknown')\n"
        ),
        uri="file:///project/templates/base.html",
    )
    plugin = DjangoUrlsPlugin()

    diagnostics = plugin.on_diagnostics(context)

    messages = [item.message for item in diagnostics]
    assert "Unknown Django URL name: 'app:missing'" in messages
    assert "Unknown Django URL name: 'app:unknown'" in messages
    assert all(item.severity == DiagnosticSeverity.Warning for item in diagnostics)
    assert all(item.source == "django-urls" for item in diagnostics)


def test_django_urls_plugin_skips_non_template_and_non_python_files():
    context = create_context(
        source="reverse('app:missing')",
        uri="file:///project/static/app.js",
    )

    diagnostics = DjangoUrlsPlugin().on_diagnostics(context)

    assert diagnostics == []
