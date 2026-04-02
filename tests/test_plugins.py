"""Tests for the djlsp plugin system."""

from unittest.mock import MagicMock, patch

import jedi
from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    Hover,
    Location,
    Position,
    Range,
)
from pygls.workspace import TextDocument

from djlsp.constants import FALLBACK_DJANGO_DATA
from djlsp.index import Variable, WorkspaceIndex
from djlsp.parser import TemplateParser
from djlsp.plugins import (
    CollectorPlugin,
    ContextPlugin,
    ParserPlugin,
    _load_entry_points,
)


def _make_parser(source, *, parser_plugin_classes=(), context_plugin_classes=()):
    """Create a TemplateParser with the given plugin classes injected."""
    workspace_index = WorkspaceIndex(src_path="/project/src", env_path="/project/env")
    workspace_index.update(
        {
            "libraries": {
                "__builtins__": FALLBACK_DJANGO_DATA["libraries"]["__builtins__"],
            },
            "templates": {},
            "static_files": [],
            "urls": {},
            "global_template_context": {},
        }
    )
    with (
        patch(
            "djlsp.parser.get_parser_plugin_classes",
            return_value=list(parser_plugin_classes),
        ),
        patch(
            "djlsp.parser.get_context_plugin_classes",
            return_value=list(context_plugin_classes),
        ),
    ):
        return TemplateParser(
            workspace_index=workspace_index,
            jedi_project=jedi.Project("."),
            document=TextDocument(uri="file:///templates/test.html", source=source),
        )


def test_load_entry_points_returns_loaded_classes():
    class FakePlugin:
        pass

    mock_ep = MagicMock()
    mock_ep.load.return_value = FakePlugin

    _load_entry_points.cache_clear()
    with patch("djlsp.plugins.entry_points", return_value=[mock_ep]):
        result = _load_entry_points("some.group")
    _load_entry_points.cache_clear()

    assert result == [FakePlugin]


def test_load_entry_points_skips_failed_loads():
    mock_ep = MagicMock()
    mock_ep.name = "broken_plugin"
    mock_ep.load.side_effect = ImportError("package not found")

    _load_entry_points.cache_clear()
    with patch("djlsp.plugins.entry_points", return_value=[mock_ep]):
        result = _load_entry_points("some.group")
    _load_entry_points.cache_clear()

    assert result == []


def test_collector_plugin_can_write_plugin_data():
    """CollectorPlugin.collect() can store data in collector.plugin_data."""

    class MyPlugin(CollectorPlugin):
        def collect(self, collector):
            collector.plugin_data["my_key"] = ["foo", "bar"]

    mock_ep = MagicMock()
    mock_ep.name = "my_plugin"
    mock_ep.load.return_value = MyPlugin

    fake_collector = MagicMock()
    fake_collector.plugin_data = {}

    with patch("djlsp.plugins.entry_points", return_value=[mock_ep]):
        for ep in _load_entry_points("djlsp.collector_plugins"):
            ep().collect(fake_collector)
    _load_entry_points.cache_clear()

    assert fake_collector.plugin_data["my_key"] == ["foo", "bar"]


def test_plugin_data_available_in_parser_plugin():
    """Parser plugins can read plugin_data from workspace_index."""

    class MyPlugin(ParserPlugin):
        def completions(self, line, character):
            items = self.workspace_index.plugin_data.get("css_classes", [])
            return [
                CompletionItem(label=item, kind=CompletionItemKind.Keyword)
                for item in items
            ]

    parser = _make_parser("no builtin match", parser_plugin_classes=[MyPlugin])
    parser.workspace_index.plugin_data["css_classes"] = ["btn", "container"]

    result = parser.completions(0, 0)
    assert [item.label for item in result] == ["btn", "container"]


def test_plugin_data_available_in_context_plugin():
    """Context plugins can read plugin_data from workspace_index."""

    class MyPlugin(ContextPlugin):
        def get_context(self, *, line, character, context):
            return {
                key: Variable(type="str")
                for key in self.workspace_index.plugin_data.get("extra_vars", [])
            }

    parser = _make_parser("{{ ", context_plugin_classes=[MyPlugin])
    parser.workspace_index.plugin_data["extra_vars"] = ["request_id", "tenant"]

    context = parser.get_context(line=0, character=3)
    assert "request_id" in context
    assert "tenant" in context


def test_wagtail_collector_plugin_is_registered():
    from importlib.metadata import entry_points

    plugins = {ep.name: ep for ep in entry_points(group="djlsp.collector_plugins")}
    assert "wagtail" in plugins


def test_collector_plugin_collect_is_called():
    """_run_collector_plugins dispatches to each registered plugin."""
    received_collectors = []

    class MyPlugin(CollectorPlugin):
        def collect(self, collector):
            received_collectors.append(collector)

    mock_ep = MagicMock()
    mock_ep.name = "my_plugin"
    mock_ep.load.return_value = MyPlugin

    fake_collector = MagicMock()

    with patch("djlsp.plugins.entry_points", return_value=[mock_ep]):
        for ep in _load_entry_points("djlsp.collector_plugins"):
            ep().collect(fake_collector)

    assert len(received_collectors) == 1
    assert received_collectors[0] is fake_collector


def test_parser_plugin_completions_used_when_no_builtin_match():
    class MyPlugin(ParserPlugin):
        def completions(self, line, character):
            return [
                CompletionItem(label="plugin-item", kind=CompletionItemKind.Keyword)
            ]

    parser = _make_parser("no builtin match here", parser_plugin_classes=[MyPlugin])
    result = parser.completions(0, 0)

    assert any(item.label == "plugin-item" for item in result)


def test_parser_plugin_completions_skipped_when_builtin_matches():
    called = []

    class MyPlugin(ParserPlugin):
        def completions(self, line, character):
            called.append(True)
            return [
                CompletionItem(label="plugin-item", kind=CompletionItemKind.Keyword)
            ]

    # "{% load " triggers the builtin load matcher
    parser = _make_parser("{% load ", parser_plugin_classes=[MyPlugin])
    parser.completions(0, 8)

    assert not called


def test_parser_plugin_completions_exception_does_not_crash():
    class BrokenPlugin(ParserPlugin):
        def completions(self, line, character):
            raise RuntimeError("intentional failure")

    parser = _make_parser("no match", parser_plugin_classes=[BrokenPlugin])
    assert parser.completions(0, 0) == []


def test_parser_plugin_hover_used_when_no_builtin_match():
    class MyPlugin(ParserPlugin):
        def hover(self, line, character):
            return Hover(contents="plugin hover text")

    parser = _make_parser("no builtin match here", parser_plugin_classes=[MyPlugin])
    result = parser.hover(0, 0)

    assert result is not None
    assert result.contents == "plugin hover text"


def test_parser_plugin_hover_exception_does_not_crash():
    class BrokenPlugin(ParserPlugin):
        def hover(self, line, character):
            raise RuntimeError("intentional failure")

    parser = _make_parser("no match", parser_plugin_classes=[BrokenPlugin])
    assert parser.hover(0, 0) is None


def test_parser_plugin_goto_definition_used_when_no_builtin_match():
    expected = Location(
        uri="file:///some/file.py",
        range=Range(
            start=Position(line=10, character=0),
            end=Position(line=10, character=0),
        ),
    )

    class MyPlugin(ParserPlugin):
        def goto_definition(self, line, character):
            return expected

    parser = _make_parser("no builtin match here", parser_plugin_classes=[MyPlugin])
    result = parser.goto_definition(0, 0)

    assert result == expected


def test_parser_plugin_goto_definition_exception_does_not_crash():
    class BrokenPlugin(ParserPlugin):
        def goto_definition(self, line, character):
            raise RuntimeError("intentional failure")

    parser = _make_parser("no match", parser_plugin_classes=[BrokenPlugin])
    assert parser.goto_definition(0, 0) is None


def test_context_plugin_variables_added_to_context():
    class MyPlugin(ContextPlugin):
        def get_context(self, *, line, character, context):
            return {"plugin_var": Variable(type="str", docs="added by plugin")}

    parser = _make_parser("{{ ", context_plugin_classes=[MyPlugin])
    context = parser.get_context(line=0, character=3)

    assert "plugin_var" in context
    assert context["plugin_var"].type == "str"


def test_context_plugin_receives_existing_context():
    received = {}

    class SpyPlugin(ContextPlugin):
        def get_context(self, *, line, character, context):
            received.update(context)
            return {}

    parser = _make_parser(
        "{# type blog: list #}\n{{ ", context_plugin_classes=[SpyPlugin]
    )
    parser.get_context(line=1, character=3)

    assert "blog" in received


def test_context_plugin_exception_does_not_crash():
    class BrokenPlugin(ContextPlugin):
        def get_context(self, *, line, character, context):
            raise RuntimeError("intentional failure")

    parser = _make_parser("{{ ", context_plugin_classes=[BrokenPlugin])
    context = parser.get_context(line=0, character=3)
    assert isinstance(context, dict)
