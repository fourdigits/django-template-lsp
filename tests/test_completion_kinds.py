"""
Test the type of completion feedback returned by diagnostic server, such as
properties, methods and keywords
"""

import pytest
from lsprotocol.types import CompletionItemKind

from tests.test_parser import create_parser


@pytest.mark.parametrize(
    "content,line_number,expected_kind",
    [
        ("{# type blog: django", 0, CompletionItemKind.Module),
        ("{% load website %}\n{{ value|up", 1, CompletionItemKind.Function),
        ("{% url 'web", 0, CompletionItemKind.Reference),
        ("{% static 'js", 0, CompletionItemKind.File),
        ("{{ bl", 0, CompletionItemKind.Variable),
        ("{# type news: str #}\n{{ news|cap", 1, CompletionItemKind.Function),
        ("{% extends 'ba", 0, CompletionItemKind.File),
        ("{% block header %}\n{% endblock ", 1, CompletionItemKind.Property),
        ("{% load w", 0, CompletionItemKind.Module),
        ("{% extends 'base.html' %}\n{% block h", 1, CompletionItemKind.Property),
        (
            "{# type customer: django.db.models.Model #}\n{{ customer.sav",
            1,
            CompletionItemKind.Function,
        ),
        (
            "{# type customer: django.db.models.Model #}\n{{ customer.objec",
            1,
            CompletionItemKind.Module,
        ),
        (
            "{# type customer: django.db.models.Model #}\n{{ customer.pk",
            1,
            CompletionItemKind.Variable,
        ),
    ],
)
def test_completion_suggestion_kind(
    content: str, line_number: int, expected_kind: CompletionItemKind
):
    parser = create_parser(content)

    lines = content.split("\n")
    target_line = lines[line_number]
    eol = len(target_line)

    completions = parser.completions(line_number, eol)
    assert completions
    assert completions[0].kind == expected_kind
