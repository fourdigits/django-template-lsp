import jedi
import pytest
from pygls.workspace import TextDocument

from djlsp.constants import FALLBACK_DJANGO_DATA
from djlsp.index import WorkspaceIndex
from djlsp.parser import TemplateParser


def create_parser(source) -> TemplateParser:
    workspace_index = WorkspaceIndex(src_path="/project/src", env_path="/project/env")
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
                        "get_homepage": {
                            "name": "get_homepage",
                            "docs": "Retrieve the homepage.",
                            "source": "src:templatetags/website.py:8",
                        },
                    },
                    "filters": {
                        "currency": {
                            "name": "currency",
                            "docs": "Formats a number as currency.",
                            "source": "src:filters.py:5",
                        },
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


###################################################################################
# Hovers
###################################################################################
def test_hover_url():
    parser = create_parser("{% url 'website:home' %}")
    hover = parser.hover(0, 12)
    assert hover is not None
    assert hover.contents == "Homepage"


def test_hover_filter():
    parser = create_parser("{% load website %}\n{{ some_variable|currency }}")
    hover = parser.hover(1, 23)
    assert hover is not None
    assert hover.contents == "Formats a number as currency."


def test_hover_tag():
    parser = create_parser("{% load website %}\n{% get_homepage %}")
    hover = parser.hover(1, 12)
    assert hover is not None
    assert hover.contents == "Retrieve the homepage."


###################################################################################
# Goto Definitions
###################################################################################
def test_goto_definition_url():
    parser = create_parser("{% url 'website:home' %}")
    definition = parser.goto_definition(0, 12)
    assert definition is not None
    assert definition.uri == "file:///project/src/views.py"
    assert definition.range.start.line == 12
    assert definition.range.start.character == 0


def test_goto_definition_filter():
    parser = create_parser("{% load website %}\n{{ some_variable|currency }}")
    definition = parser.goto_definition(1, 25)
    assert definition is not None
    assert definition.uri == "file:///project/src/filters.py"
    assert definition.range.start.line == 5
    assert definition.range.start.character == 0


def test_goto_definition_tag():
    parser = create_parser("{% load website %}\n{% get_homepage %}")
    definition = parser.goto_definition(1, 14)
    assert definition is not None
    assert definition.uri == "file:///project/src/templatetags/website.py"
    assert definition.range.start.line == 8
    assert definition.range.start.character == 0


@pytest.mark.parametrize(
    "content",
    [
        """{% extends 'base.html' %}""",
        """{% extends "base.html" %}""",
        """{% include 'base.html' %}""",
        """{% include "base.html" %}""",
    ],
)
def test_goto_definition_template(content):
    parser = create_parser(content)
    definition = parser.goto_definition(0, 16)
    assert definition is not None
    assert definition.uri == "file:///project/src/templates/base.html"
    assert definition.range.start.line == 0
    assert definition.range.start.character == 0
