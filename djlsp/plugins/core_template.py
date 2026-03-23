from lsprotocol.types import CompletionItem

from djlsp.parser import TemplateParser
from djlsp.plugins.base import Plugin, PluginContext


class CoreTemplatePlugin(Plugin):
    name = "core-template"
    priority = 100

    def _parser(self, context: PluginContext) -> TemplateParser:
        return TemplateParser(
            workspace_index=context.workspace_index,
            jedi_project=context.jedi_project,
            document=context.document,
        )

    def on_completions(
        self, context: PluginContext, *, line: int, character: int
    ) -> list[CompletionItem]:
        return self._parser(context).completions(line, character)

    def on_hover(self, context: PluginContext, *, line: int, character: int):
        return self._parser(context).hover(line, character)

    def on_definition(self, context: PluginContext, *, line: int, character: int):
        return self._parser(context).goto_definition(line, character)

    def on_completion_resolve(self, item: CompletionItem) -> CompletionItem | None:
        return TemplateParser.resolve_completion(item)
