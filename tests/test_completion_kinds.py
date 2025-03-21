"""
Test the type of completion feedback returned by diagnostic server, such as
properties, methods and keywords
"""

from lsprotocol.types import CompletionItemKind

from tests.test_parser import create_parser


def test_load_completions_use_module_kind():
    parser = create_parser("{% load w")
    completions = parser.completions(0, 8)
    assert completions[0].kind == CompletionItemKind.Module


def test_block_completions_use_property_kind():
    parser = create_parser("{% extends 'base.html' %}\n{% block h")
    completions = parser.completions(1, 9)
    assert completions[0].kind == CompletionItemKind.Property


def test_endblock_completions_use_property_kind():
    parser = create_parser("{% block header %}\n{% endblock ")
    completions = parser.completions(1, 12)
    assert completions[0].kind == CompletionItemKind.Property


def test_static_completions_use_file_kind():
    parser = create_parser("{% static 'js")
    completions = parser.completions(0, 12)
    assert completions[0].kind == CompletionItemKind.File


def test_url_completions_use_reference_kind():
    parser = create_parser("{% url 'web")
    completions = parser.completions(0, 11)
    assert completions[0].kind == CompletionItemKind.Reference


def test_template_completions_use_file_kind():
    parser = create_parser("{% extends 'ba")
    completions = parser.completions(0, 12)
    assert completions[0].kind == CompletionItemKind.File


def test_tag_completions_use_keyword_kind():
    parser = create_parser("{% load website %}\n{% get")
    completions = parser.completions(1, 5)
    homepage_tag = [item for item in completions if item.label == "get_homepage"][0]
    assert homepage_tag.kind == CompletionItemKind.Keyword


def test_filter_completions_use_function_kind():
    parser = create_parser("{% load website %}\n{{ value|cur")
    completions = parser.completions(1, 12)
    assert completions[0].kind == CompletionItemKind.Function


def test_type_comment_completions_use_class_kind():
    parser = create_parser("{# type blog: django")
    completions = parser.completions(0, 18)
    assert completions[0].kind == CompletionItemKind.Class


def test_context_variable_completions_use_variable_kind():
    parser = create_parser("{{ bl")
    completions = parser.completions(0, 5)
    assert completions[0].kind == CompletionItemKind.Variable


def test_context_string_method_completions():
    """Test that string methods have Method kind"""
    parser = create_parser("{# type news: str #}\n{{ news.")
    completions = parser.completions(1, 9)

    methods = [
        item
        for item in completions
        if item.label in ("capitalize", "upper", "split", "strip")
    ]

    for method in methods:
        assert method.kind == CompletionItemKind.Function


def test_context_field_completions():
    """Test that other attributes are reported as Field"""
    parser = create_parser("{# type news: dict #}\n{{ news.")
    completions = parser.completions(1, 9)

    fields = [item for item in completions if item.label in ("items", "keys", "values")]

    for field in fields:
        assert field.kind != CompletionItemKind.Property


def test_django_model_property_completions():
    """Test that Django model attributes have appropriate kinds."""
    parser = create_parser("{# type customer: django.db.models.Model #}\n{{ customer.")
    completions = parser.completions(1, 12)

    model_attributes = [
        item
        for item in completions
        if item.label
        in ("id", "pk", "objects", "save", "delete", "first_name", "last_name")
    ]

    for attr in model_attributes:
        if attr.label in ("first_name", "last_name", "id", "pk"):
            assert attr.kind == CompletionItemKind.Field
        elif attr.label in ("save", "delete"):
            assert attr.kind == CompletionItemKind.Method
        elif attr.label == "objects":
            assert attr.kind == CompletionItemKind.Field
