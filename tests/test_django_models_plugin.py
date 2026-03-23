import jedi
from lsprotocol.types import DiagnosticSeverity
from pygls.workspace import TextDocument

from djlsp.index import WorkspaceIndex
from djlsp.plugins import DjangoModelsPlugin, PluginContext


def create_context(*, source: str) -> PluginContext:
    return PluginContext(
        workspace_index=WorkspaceIndex(),
        jedi_project=jedi.Project("."),
        document=TextDocument(uri="file:///project/admin.py", source=source),
    )


def create_plugin() -> DjangoModelsPlugin:
    mapping = {
        "Book": {"id", "title", "author"},
        "Article": {"id", "headline", "body"},
    }
    return DjangoModelsPlugin(
        model_fields_provider=lambda _context, model_name: mapping.get(
            model_name, set()
        )
    )


def test_django_models_plugin_completes_model_admin_list_display_fields():
    context = create_context(
        source=(
            "class BookAdmin(admin.ModelAdmin):\n"
            "    model = Book\n"
            "    list_display = ('ti',)\n"
        )
    )
    plugin = create_plugin()

    items = plugin.on_completions(context, line=2, character=23)

    assert [item.label for item in items] == ["title"]


def test_django_models_plugin_completes_modelform_meta_fields():
    context = create_context(
        source=(
            "class ArticleForm(forms.ModelForm):\n"
            "    class Meta:\n"
            "        model = Article\n"
            "        fields = ('hea',)\n"
        )
    )
    plugin = create_plugin()

    items = plugin.on_completions(context, line=3, character=22)

    assert [item.label for item in items] == ["headline"]


def test_django_models_plugin_reports_unknown_model_fields():
    context = create_context(
        source=(
            "class BookAdmin(admin.ModelAdmin):\n"
            "    model = Book\n"
            "    list_display = ('title', 'missing')\n"
            "\n"
            "class ArticleForm(forms.ModelForm):\n"
            "    class Meta:\n"
            "        model = Article\n"
            "        fields = ('headline', 'oops')\n"
        )
    )
    plugin = create_plugin()

    diagnostics = plugin.on_diagnostics(context)
    messages = [item.message for item in diagnostics]

    assert "Unknown field 'missing' on model 'Book'" in messages
    assert "Unknown field 'oops' on model 'Article'" in messages
    assert all(item.severity == DiagnosticSeverity.Warning for item in diagnostics)
    assert all(item.source == "django-models" for item in diagnostics)


def test_django_models_plugin_skips_non_python_documents():
    context = PluginContext(
        workspace_index=WorkspaceIndex(),
        jedi_project=jedi.Project("."),
        document=TextDocument(
            uri="file:///project/templates/base.html",
            source="{{ book.title }}",
        ),
    )
    plugin = create_plugin()

    assert plugin.on_completions(context, line=0, character=5) == []
    assert plugin.on_diagnostics(context) == []
