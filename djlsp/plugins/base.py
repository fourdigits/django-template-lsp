from dataclasses import dataclass, field

import jedi
from lsprotocol.types import CompletionItem, Hover, Location
from pygls.workspace import TextDocument

from djlsp.index import WorkspaceIndex

PLUGIN_API_VERSION = 1


@dataclass(frozen=True)
class PluginContext:
    workspace_index: WorkspaceIndex
    jedi_project: jedi.Project
    document: TextDocument
    settings: dict = field(default_factory=dict)


class Plugin:
    name = ""
    api_version = PLUGIN_API_VERSION
    priority = 100
    default_enabled = True

    def on_completions(
        self, context: PluginContext, *, line: int, character: int
    ) -> list[CompletionItem]:
        return []

    def on_hover(
        self, context: PluginContext, *, line: int, character: int
    ) -> Hover | None:
        return None

    def on_definition(
        self, context: PluginContext, *, line: int, character: int
    ) -> Location | None:
        return None

    def on_completion_resolve(self, item: CompletionItem) -> CompletionItem | None:
        return None

    def on_diagnostics(self, context: PluginContext):
        return []

    def on_code_actions(self, context: PluginContext):
        return []
