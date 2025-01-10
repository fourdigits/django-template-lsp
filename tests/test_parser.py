import jedi
from pygls.workspace import TextDocument

from djlsp.constants import FALLBACK_DJANGO_DATA
from djlsp.index import WorkspaceIndex
from djlsp.parser import TemplateParser


def create_parser(source) -> TemplateParser:
    workspace_index = WorkspaceIndex()
    workspace_index.update(
        {
            "static_files": ["js/main.js", "css/main.css"],
            "urls": {
                "website:home": {
                    "docs": "Homepage",
                    "source": "src:views.py:12",
                },
                "blog:list": {
                    "docs": "Blog list",
                    "source": "src:views.py:22",
                },
                "blog:detail": {
                    "docs": "Blog detail",
                    "source": "src:views.py:32",
                },
            },
            "libraries": {
                "__builtins__": FALLBACK_DJANGO_DATA["libraries"]["__builtins__"],
                "website": {
                    "tags": {
                        "get_homepage": {},
                    },
                    "filters": {
                        "currency": {},
                    },
                },
            },
            "templates": {
                "base.html": {
                    "path": "src:templates/base.html",
                    "blocks": ["header", "content"],
                },
                "blog/list.html": {
                    "path": "src:templates/blog/list.html",
                    "extends": "base.html",
                },
            },
        }
    )

    return TemplateParser(
        workspace_index=workspace_index,
        jedi_project=jedi.Project("."),
        document=TextDocument(
            uri="file:///templates/test.html",
            source=source,
        ),
    )


def test_completion_tags_builtins():
    parser = create_parser("{% url")
    assert any(item.label == "load" for item in parser.completions(0, 2))
    items = parser.completions(0, 4)
    assert items
    assert all([item.label.startswith("ur") for item in items])


def test_completion_tags_missing_load():
    parser = create_parser("{% ")
    assert not any(item.label == "get_homepage" for item in parser.completions(0, 2))


def test_completion_tags():
    parser = create_parser("{% load website %}\n{% ")
    assert any(item.label == "get_homepage" for item in parser.completions(1, 2))
