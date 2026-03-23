import ast
from dataclasses import dataclass
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


@dataclass(frozen=True)
class FieldReference:
    model_name: str
    field_name: str
    line: int
    content_start_col: int
    content_end_col: int

    def contains(self, *, line: int, character: int) -> bool:
        return (
            self.line == line
            and self.content_start_col <= character <= self.content_end_col
        )


class DjangoModelsPlugin(Plugin):
    name = "django-models"
    priority = 140

    def __init__(
        self,
        *,
        model_fields_provider: Callable[[PluginContext, str], set[str]] | None = None,
    ):
        self._model_fields_provider = (
            model_fields_provider or self._default_model_fields
        )

    def _default_model_fields(
        self, context: PluginContext, model_name: str
    ) -> set[str]:
        try:
            from django.apps import apps
        except Exception:
            return set()

        matching_models = [
            model for model in apps.get_models() if model.__name__ == model_name
        ]
        if len(matching_models) != 1:
            return set()
        model = matching_models[0]
        return {
            field.name
            for field in model._meta.get_fields()
            if getattr(field, "name", None)
        }

    def _is_python_document(self, context: PluginContext) -> bool:
        return Path(context.document.path).suffix == ".py"

    def _parse(self, context: PluginContext) -> ast.Module | None:
        try:
            return ast.parse(context.document.source)
        except SyntaxError:
            return None

    def _extract_model_name(self, body: list[ast.stmt]) -> str | None:
        for statement in body:
            if not isinstance(statement, ast.Assign) or len(statement.targets) != 1:
                continue
            target = statement.targets[0]
            if not isinstance(target, ast.Name) or target.id != "model":
                continue
            if isinstance(statement.value, ast.Name):
                return statement.value.id
            if isinstance(statement.value, ast.Attribute):
                return statement.value.attr
        return None

    def _string_references_from_assignment(
        self, node: ast.Assign, *, model_name: str
    ) -> list[FieldReference]:
        references: list[FieldReference] = []
        if not isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
            return references

        for value in node.value.elts:
            if not (
                isinstance(value, ast.Constant)
                and isinstance(value.value, str)
                and value.lineno is not None
                and value.col_offset is not None
                and value.end_col_offset is not None
            ):
                continue

            # AST positions include quotes for string constants.
            references.append(
                FieldReference(
                    model_name=model_name,
                    field_name=value.value,
                    line=value.lineno - 1,
                    content_start_col=value.col_offset + 1,
                    content_end_col=max(value.col_offset + 1, value.end_col_offset - 1),
                )
            )
        return references

    def _extract_references(self, context: PluginContext) -> list[FieldReference]:
        tree = self._parse(context)
        if tree is None:
            return []

        references: list[FieldReference] = []
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue

            base_names = {
                base.id
                for base in node.bases
                if isinstance(base, ast.Name)
            } | {
                base.attr
                for base in node.bases
                if isinstance(base, ast.Attribute)
            }
            is_model_admin = "ModelAdmin" in base_names
            is_model_form = "ModelForm" in base_names

            if is_model_admin:
                model_name = self._extract_model_name(node.body)
                if not model_name:
                    continue
                for statement in node.body:
                    if not (
                        isinstance(statement, ast.Assign)
                        and len(statement.targets) == 1
                    ):
                        continue
                    target = statement.targets[0]
                    if not isinstance(target, ast.Name) or target.id != "list_display":
                        continue
                    references.extend(
                        self._string_references_from_assignment(
                            statement, model_name=model_name
                        )
                    )

            if is_model_form:
                for statement in node.body:
                    if not (
                        isinstance(statement, ast.ClassDef) and statement.name == "Meta"
                    ):
                        continue
                    model_name = self._extract_model_name(statement.body)
                    if not model_name:
                        continue
                    for meta_statement in statement.body:
                        if (
                            isinstance(meta_statement, ast.Assign)
                            and len(meta_statement.targets) == 1
                            and isinstance(meta_statement.targets[0], ast.Name)
                            and meta_statement.targets[0].id == "fields"
                        ):
                            if (
                                isinstance(meta_statement.value, ast.Constant)
                                and meta_statement.value.value == "__all__"
                            ):
                                continue
                            references.extend(
                                self._string_references_from_assignment(
                                    meta_statement, model_name=model_name
                                )
                            )
        return references

    def on_completions(
        self, context: PluginContext, *, line: int, character: int
    ) -> list[CompletionItem]:
        if not self._is_python_document(context):
            return []

        for reference in self._extract_references(context):
            if not reference.contains(line=line, character=character):
                continue
            prefix = context.document.lines[line][
                reference.content_start_col:character
            ]
            model_fields = self._model_fields_provider(context, reference.model_name)
            return [
                CompletionItem(
                    label=field_name,
                    kind=CompletionItemKind.Field,
                )
                for field_name in sorted(model_fields)
                if field_name.startswith(prefix)
            ]
        return []

    def on_diagnostics(self, context: PluginContext) -> list[Diagnostic]:
        if not self._is_python_document(context):
            return []

        diagnostics: list[Diagnostic] = []
        for reference in self._extract_references(context):
            model_fields = self._model_fields_provider(context, reference.model_name)
            if not model_fields or reference.field_name in model_fields:
                continue

            diagnostics.append(
                Diagnostic(
                    range=Range(
                        start=Position(
                            line=reference.line, character=reference.content_start_col
                        ),
                        end=Position(
                            line=reference.line, character=reference.content_end_col
                        ),
                    ),
                    severity=DiagnosticSeverity.Warning,
                    source=self.name,
                    message=(
                        f"Unknown field '{reference.field_name}' on model "
                        f"'{reference.model_name}'"
                    ),
                )
            )
        return diagnostics
