import json
import sys
from functools import lru_cache
from pathlib import Path
from subprocess import check_output

import jedi
import pytest
from pygls.workspace import TextDocument

from djlsp.index import WorkspaceIndex
from djlsp.parser import TemplateParser
from djlsp.server import DJANGO_COLLECTOR_SCRIPT_PATH
from tests.test_django_collector import (
    DJANGO_TEST_PROJECT_SRC,
    DJANGO_TEST_SETTINGS_MODULE,
)
from tests.test_parser import create_parser


@lru_cache
def collect_sample_project_data() -> dict:
    return json.loads(
        check_output(
            [
                sys.executable,
                DJANGO_COLLECTOR_SCRIPT_PATH,
                f"--django-settings-module={DJANGO_TEST_SETTINGS_MODULE}",
                f"--project-src={DJANGO_TEST_PROJECT_SRC}",
            ]
        )
    )


def create_sample_project_parser(source: str) -> TemplateParser:
    workspace_index = WorkspaceIndex(
        src_path=DJANGO_TEST_PROJECT_SRC,
        env_path=sys.prefix,
    )
    workspace_index.update(collect_sample_project_data())
    return TemplateParser(
        workspace_index=workspace_index,
        jedi_project=jedi.Project(
            path=DJANGO_TEST_PROJECT_SRC,
            environment_path=sys.prefix,
        ),
        document=TextDocument(
            uri=Path(
                DJANGO_TEST_PROJECT_SRC,
                "django_app",
                "templates",
                "django_app.html",
            ).as_uri(),
            source=source,
        ),
    )


def test_sample_project_behavior_baseline():
    parser = create_sample_project_parser(
        "\n".join(
            [
                "{% load django_app %}",
                "{% dja",
                "{{ value|django_app_",
                "{% url 'django_app:",
                "{% static 'django_app",
            ]
        )
    )

    assert any(item.label == "django_app_tag" for item in parser.completions(1, 6))
    assert any(item.label == "django_app_filter" for item in parser.completions(2, 20))
    assert any(item.label == "django_app:index" for item in parser.completions(3, 18))
    assert any(item.label == "django_app.js" for item in parser.completions(4, 24))


def test_sample_project_hover_and_definition_baseline():
    parser = create_sample_project_parser("{% load django_app %}\n{% django_app_tag %}")

    hover = parser.hover(1, 16)
    assert hover is not None
    assert hover.contents == "Docs for tag"

    definition = parser.goto_definition(1, 16)
    assert definition is not None
    assert (
        definition.uri
        == Path(
            DJANGO_TEST_PROJECT_SRC,
            "django_app",
            "templatetags",
            "django_app.py",
        ).as_uri()
    )
    assert definition.range.start.line == 6
    assert definition.range.start.character == 0


@pytest.mark.parametrize(
    ("content", "line", "character"),
    [
        ("{% if ", 0, 6),
        ("{% for item in blog %}\n{% endwith", 1, 10),
        ("{% with blog_alias=blog %}\n{{ blog_alias.", 1, 14),
        ("{% load website %}\n{% block content %}\n{{ blog.0.", 2, 10),
    ],
)
def test_malformed_template_inputs_do_not_crash(content, line, character):
    parser = create_parser(content)

    completions = parser.completions(line, character)
    hover = parser.hover(line, character)
    definition = parser.goto_definition(line, character)

    assert isinstance(completions, list)
    assert hover is None or hover.contents is not None
    assert definition is None or definition.uri
