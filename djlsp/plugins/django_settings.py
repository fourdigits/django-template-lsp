import re
from pathlib import Path
from typing import Callable

from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
)

from djlsp.plugins.base import Plugin, PluginContext


class DjangoSettingsPlugin(Plugin):
    name = "django-settings"
    priority = 130

    _RE_TEMPLATE_COMPLETION = re.compile(r".*{{\s*settings\.([A-Z0-9_]*)$")
    _RE_PYTHON_COMPLETION = re.compile(r".*\bsettings\.([A-Z0-9_]*)$")
    _RE_TEMPLATE_USAGE = re.compile(r"{{\s*settings\.([A-Z][A-Z0-9_]*)")
    _RE_PYTHON_USAGE = re.compile(r"\bsettings\.([A-Z][A-Z0-9_]*)")

    def __init__(
        self,
        *,
        settings_keys_provider: Callable[[PluginContext], set[str]] | None = None,
    ):
        self._settings_keys_provider = settings_keys_provider or self._default_keys

    def _is_python_document(self, context: PluginContext) -> bool:
        return Path(context.document.path).suffix == ".py"

    def _is_template_document(self, context: PluginContext) -> bool:
        path = context.document.path
        return "/templates/" in path or Path(path).suffix in {".html", ".jinja", ".j2"}

    def _default_keys(self, context: PluginContext) -> set[str]:
        keys: set[str] = set()
        extra_keys = context.settings.get("extra_keys")
        if isinstance(extra_keys, list):
            keys.update(str(key) for key in extra_keys if isinstance(key, str))

        try:
            from django.conf import settings as django_settings

            keys.update(name for name in dir(django_settings) if name.isupper())
        except Exception:
            # When Django settings are unavailable, only use configured extras.
            pass
        return keys

    def on_completions(
        self, context: PluginContext, *, line: int, character: int
    ) -> list[CompletionItem]:
        keys = self._settings_keys_provider(context)
        if not keys:
            return []

        line_fragment = context.document.lines[line][:character]
        prefix = None
        if self._is_template_document(context):
            if match := self._RE_TEMPLATE_COMPLETION.match(line_fragment):
                prefix = match.group(1)
        elif self._is_python_document(context):
            if match := self._RE_PYTHON_COMPLETION.match(line_fragment):
                prefix = match.group(1)
        else:
            return []

        if prefix is None:
            return []

        return [
            CompletionItem(label=key, kind=CompletionItemKind.Constant)
            for key in sorted(keys)
            if key.startswith(prefix)
        ]

    def on_diagnostics(self, context: PluginContext) -> list[Diagnostic]:
        if not (
            self._is_template_document(context) or self._is_python_document(context)
        ):
            return []

        keys = self._settings_keys_provider(context)
        if not keys:
            return []

        source = context.document.source
        patterns = [self._RE_TEMPLATE_USAGE, self._RE_PYTHON_USAGE]
        diagnostics: list[Diagnostic] = []
        seen: set[tuple] = set()

        for pattern in patterns:
            for match in pattern.finditer(source):
                key = match.group(1)
                if key in keys:
                    continue

                start_offset = match.start(1)
                end_offset = match.end(1)
                start_line = source.count("\n", 0, start_offset)
                end_line = source.count("\n", 0, end_offset)
                line_start = source.rfind("\n", 0, start_offset) + 1
                line_end = source.rfind("\n", 0, end_offset) + 1
                start_char = start_offset - line_start
                end_char = end_offset - line_end

                dedupe_key = (start_line, start_char, end_line, end_char, key)
                if dedupe_key in seen:
                    continue
                seen.add(dedupe_key)

                diagnostics.append(
                    Diagnostic(
                        range=Range(
                            start=Position(line=start_line, character=start_char),
                            end=Position(line=end_line, character=end_char),
                        ),
                        severity=DiagnosticSeverity.Warning,
                        source=self.name,
                        message=f"Unknown Django setting key: '{key}'",
                    )
                )

        return diagnostics
