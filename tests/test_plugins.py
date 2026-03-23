import jedi
from lsprotocol.types import CompletionItem, CompletionItemKind, Hover
from pygls.workspace import TextDocument

from djlsp.index import WorkspaceIndex
from djlsp.plugins import Plugin, PluginContext, PluginManager


def create_context() -> PluginContext:
    return PluginContext(
        workspace_index=WorkspaceIndex(),
        jedi_project=jedi.Project("."),
        document=TextDocument(uri="file:///templates/test.html", source="{{ x }}"),
    )


class CompletionPluginA(Plugin):
    name = "completion-a"
    priority = 10

    def on_completions(self, context: PluginContext, *, line: int, character: int):
        return [
            CompletionItem(label="shared", kind=CompletionItemKind.Variable),
            CompletionItem(label="a-only", kind=CompletionItemKind.Variable),
        ]


class CompletionPluginB(Plugin):
    name = "completion-b"
    priority = 20

    def on_completions(self, context: PluginContext, *, line: int, character: int):
        return [
            CompletionItem(label="shared", kind=CompletionItemKind.Variable),
            CompletionItem(label="b-only", kind=CompletionItemKind.Variable),
        ]


class HoverPluginA(Plugin):
    name = "hover-a"
    priority = 5

    def on_hover(self, context: PluginContext, *, line: int, character: int):
        return Hover(contents="a")


class HoverPluginB(Plugin):
    name = "hover-b"
    priority = 10

    def on_hover(self, context: PluginContext, *, line: int, character: int):
        return Hover(contents="b")


class BrokenPlugin(Plugin):
    name = "broken"

    def on_completions(self, context: PluginContext, *, line: int, character: int):
        raise RuntimeError("boom")


class IncompatiblePlugin(Plugin):
    name = "incompatible"
    api_version = 999

    def on_completions(self, context: PluginContext, *, line: int, character: int):
        return [CompletionItem(label="incompatible")]


def test_plugin_manager_merges_and_dedupes_completions():
    manager = PluginManager(plugins=[CompletionPluginA(), CompletionPluginB()])

    result = manager.completions(create_context(), line=0, character=4)
    labels = [item.label for item in result]

    assert labels == ["shared", "a-only", "b-only"]


def test_plugin_manager_prefers_high_priority_hover():
    manager = PluginManager(plugins=[HoverPluginB(), HoverPluginA()])

    hover = manager.hover(create_context(), line=0, character=4)

    assert hover is not None
    assert hover.contents == "a"


def test_plugin_manager_disables_failing_plugin():
    manager = PluginManager(plugins=[BrokenPlugin()], max_failures=1)

    result = manager.completions(create_context(), line=0, character=4)

    assert result == []
    assert "broken" in manager.disabled_plugins


def test_plugin_manager_skips_incompatible_plugin():
    manager = PluginManager(plugins=[IncompatiblePlugin()])

    result = manager.completions(create_context(), line=0, character=4)

    assert result == []


def test_plugin_manager_respects_enabled_and_disabled_config():
    manager = PluginManager(plugins=[CompletionPluginA(), CompletionPluginB()])
    manager.configure(options={"enabled": ["completion-b"], "disabled": []})

    result = manager.completions(create_context(), line=0, character=4)

    assert [item.label for item in result] == ["shared", "b-only"]
