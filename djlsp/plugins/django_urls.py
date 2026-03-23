import re
from pathlib import Path

from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
)

from djlsp.plugins.base import Plugin, PluginContext


class DjangoUrlsPlugin(Plugin):
    name = "django-urls"
    priority = 120

    _RE_TEMPLATE_URL_COMPLETION = re.compile(r""".*{% ?url ('|")([\w\-:]*)$""")
    _RE_TEMPLATE_URL_USAGE = re.compile(r"""{% ?url ['"]([\w:-]+)['"]""")
    _RE_PYTHON_URL_COMPLETION = re.compile(
        r""".*\b(?:reverse|reverse_lazy|redirect|resolve_url)\(\s*['"]([\w:-]*)$"""
    )
    _RE_PYTHON_URL_USAGE = re.compile(
        r"""\b(?:reverse|reverse_lazy|redirect|resolve_url)\(\s*['"]([\w:-]+)['"]"""
    )

    def _is_python_document(self, context: PluginContext) -> bool:
        return Path(context.document.path).suffix == ".py"

    def _is_template_document(self, context: PluginContext) -> bool:
        path = context.document.path
        return "/templates/" in path or Path(path).suffix in {".html", ".jinja", ".j2"}

    def on_completions(
        self, context: PluginContext, *, line: int, character: int
    ) -> list[CompletionItem]:
        line_fragment = context.document.lines[line][:character]
        prefix = None

        if self._is_template_document(context):
            if match := self._RE_TEMPLATE_URL_COMPLETION.match(line_fragment):
                prefix = match.group(2)
        elif self._is_python_document(context):
            if match := self._RE_PYTHON_URL_COMPLETION.match(line_fragment):
                prefix = match.group(1)
        else:
            return []

        if prefix is None:
            return []

        return [
            CompletionItem(
                label=url.name,
                documentation=url.docs,
                kind=CompletionItemKind.Reference,
            )
            for url in context.workspace_index.urls.values()
            if url.name.startswith(prefix)
        ]

    def on_diagnostics(self, context: PluginContext) -> list[Diagnostic]:
        if not (
            self._is_template_document(context) or self._is_python_document(context)
        ):
            return []

        source = context.document.source
        known_urls = set(context.workspace_index.urls.keys())
        diagnostics: list[Diagnostic] = []
        seen: set[tuple] = set()

        patterns = [self._RE_TEMPLATE_URL_USAGE, self._RE_PYTHON_URL_USAGE]
        for pattern in patterns:
            for match in pattern.finditer(source):
                url_name = match.group(1)
                if url_name in known_urls:
                    continue

                start_offset = match.start(1)
                end_offset = match.end(1)
                start_line = source.count("\n", 0, start_offset)
                end_line = source.count("\n", 0, end_offset)
                line_start = source.rfind("\n", 0, start_offset) + 1
                line_end = source.rfind("\n", 0, end_offset) + 1
                start_char = start_offset - line_start
                end_char = end_offset - line_end

                key = (start_line, start_char, end_line, end_char, url_name)
                if key in seen:
                    continue
                seen.add(key)

                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=start_line, character=start_char),
                            end=Position(line=end_line, character=end_char),
                        ),
                        severity=DiagnosticSeverity.Warning,
                        source=self.name,
                        message=f"Unknown Django URL name: '{url_name}'",
                    )
                )

        return diagnostics
