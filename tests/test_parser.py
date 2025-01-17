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
                    "context": {"blog": None},
                },
            },
        }
    )

    return TemplateParser(
        workspace_index=workspace_index,
        jedi_project=jedi.Project("."),
        document=TextDocument(
            uri="file:///templates/blog/list.html",
            source=source,
        ),
    )


###################################################################################
# Completions
###################################################################################
def test_completion_load():
    parser = create_parser("{% load w")
    assert any(item.label == "website" for item in parser.completions(0, 8))


def test_completion_block():
    parser = create_parser("{% extends 'base.html' %}\n{% block h}")
    assert any(item.label == "header" for item in parser.completions(1, 9))


def test_completion_block_no_used_block():
    parser = create_parser(
        "{% extends 'base.html' %}\n{% block header %}{% endblock }%\n{% block h}"
    )
    assert not any(item.label == "header" for item in parser.completions(2, 9))


def test_completion_endblock():
    parser = create_parser("{% block new %}\n{% endblock  ")
    assert any(item.label == "new" for item in parser.completions(1, 12))


def test_completion_url():
    parser = create_parser("{% url 'bl")
    assert any(item.label == "website:home" for item in parser.completions(0, 8))
    items = parser.completions(0, 9)
    assert items
    assert all(item.label.startswith("blog") for item in items)


def test_completion_static():
    parser = create_parser("{% static 'js")
    assert any(item.label == "js/main.js" for item in parser.completions(0, 12))
    items = parser.completions(0, 14)
    assert items
    assert all(item.label.startswith("js") for item in items)


def test_completion_templates_extends():
    parser = create_parser("{% extends 'ba")
    assert any(item.label == "blog/list.html" for item in parser.completions(0, 12))
    items = parser.completions(0, 14)
    assert items
    assert all(item.label.startswith("ba") for item in items)


def test_completion_templates_include():
    parser = create_parser("{% include 'ba")
    assert any(item.label == "blog/list.html" for item in parser.completions(0, 12))
    items = parser.completions(0, 14)
    assert items
    assert all(item.label.startswith("ba") for item in items)


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


def test_completion_filter():
    parser = create_parser("{% load website %}\n{{some|cur}}")
    assert any(item.label == "currency" for item in parser.completions(1, 10))


def test_completion_filter_missing_load():
    parser = create_parser("{{some|cur}}")
    assert not any(item.label == "currency" for item in parser.completions(0, 10))


def test_completion_comment():
    parser = create_parser("{# type blog: dj }")
    assert any(item.label == "djlsp" for item in parser.completions(0, 16))


def test_completion_context():
    parser = create_parser("{{ bl")
    assert any(item.label == "blog" for item in parser.completions(0, 5))


def test_completion_context_based_type_hint_comment():
    parser = create_parser("{# type news: str #}\n{{ news.cap")
    assert any(item.label == "news" for item in parser.completions(1, 5))
    assert any(item.label == "capitalize" for item in parser.completions(1, 10))
