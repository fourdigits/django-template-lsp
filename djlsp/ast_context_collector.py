import ast
import inspect
import logging
import textwrap
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)

_CONTEXT_METHOD_NAMES = {"get_context_data", "get_context"}


@dataclass(frozen=True)
class FunctionRenderContext:
    template_name: str
    context_keys: set[str]


class AstContextCollector:
    def _unwrap_callable(self, value):
        while hasattr(value, "__wrapped__"):
            value = value.__wrapped__
        return value

    def extract_context_keys(self, view: type) -> set[str]:
        view = self._unwrap_callable(view)
        try:
            source = textwrap.dedent(inspect.getsource(view))
            tree = ast.parse(source)
        except Exception:
            logger.debug("Could not parse view source for AST context", exc_info=True)
            return set()

        class_node = self._find_class_node(tree, view.__name__)
        if class_node is None:
            return set()

        keys: set[str] = set()
        for item in class_node.body:
            if isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                if item.name in _CONTEXT_METHOD_NAMES:
                    keys.update(self._extract_keys_from_method(item))
        return keys

    def extract_function_render_contexts(
        self, view: Callable[..., object]
    ) -> list[FunctionRenderContext]:
        view = self._unwrap_callable(view)
        try:
            source = textwrap.dedent(inspect.getsource(view))
            tree = ast.parse(source)
        except Exception:
            logger.debug(
                "Could not parse function view source for AST context",
                exc_info=True,
            )
            return []

        function_node = self._find_function_node(tree, view.__name__)
        if function_node is None:
            return []

        mapping_alias_keys: dict[str, set[str]] = {}
        collected: dict[str, set[str]] = {}
        self._collect_render_contexts_from_statements(
            function_node.body,
            mapping_alias_keys=mapping_alias_keys,
            collected=collected,
        )
        return [
            FunctionRenderContext(template_name=name, context_keys=keys)
            for name, keys in collected.items()
        ]

    def _find_class_node(self, tree: ast.Module, name: str) -> ast.ClassDef | None:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                return node
        return None

    def _find_function_node(
        self, tree: ast.Module, name: str
    ) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        for node in tree.body:
            if (
                isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
                and node.name == name
            ):
                return node
        return None

    def _collect_render_contexts_from_statements(
        self,
        statements: list[ast.stmt],
        *,
        mapping_alias_keys: dict[str, set[str]],
        collected: dict[str, set[str]],
    ) -> None:
        for statement in statements:
            if isinstance(statement, ast.Assign):
                self._update_mapping_aliases_from_assignment(
                    statement,
                    mapping_alias_keys,
                )
            elif isinstance(statement, ast.AnnAssign):
                self._update_mapping_aliases_from_ann_assignment(
                    statement,
                    mapping_alias_keys,
                )
            elif isinstance(statement, ast.If):
                self._collect_render_contexts_from_statements(
                    statement.body,
                    mapping_alias_keys=dict(mapping_alias_keys),
                    collected=collected,
                )
                self._collect_render_contexts_from_statements(
                    statement.orelse,
                    mapping_alias_keys=dict(mapping_alias_keys),
                    collected=collected,
                )
            elif isinstance(statement, ast.With | ast.AsyncWith):
                self._collect_render_contexts_from_statements(
                    statement.body,
                    mapping_alias_keys=dict(mapping_alias_keys),
                    collected=collected,
                )
            elif isinstance(statement, ast.For | ast.AsyncFor | ast.While):
                self._collect_render_contexts_from_statements(
                    statement.body,
                    mapping_alias_keys=dict(mapping_alias_keys),
                    collected=collected,
                )
                self._collect_render_contexts_from_statements(
                    statement.orelse,
                    mapping_alias_keys=dict(mapping_alias_keys),
                    collected=collected,
                )
            elif isinstance(statement, ast.Try):
                for body in (
                    statement.body,
                    statement.orelse,
                    statement.finalbody,
                    *(handler.body for handler in statement.handlers),
                ):
                    self._collect_render_contexts_from_statements(
                        body,
                        mapping_alias_keys=dict(mapping_alias_keys),
                        collected=collected,
                    )

            call = None
            if isinstance(statement, ast.Return):
                call = self._extract_render_call(statement.value)
            elif isinstance(statement, ast.Expr):
                call = self._extract_render_call(statement.value)
            if call:
                template_name, context_keys = self._extract_render_call_context(
                    call,
                    mapping_alias_keys=mapping_alias_keys,
                )
                if template_name and context_keys:
                    collected.setdefault(template_name, set()).update(context_keys)

    def _extract_render_call(self, node: ast.AST | None) -> ast.Call | None:
        if isinstance(node, ast.Await):
            node = node.value
        if not isinstance(node, ast.Call):
            return None

        if isinstance(node.func, ast.Name) and node.func.id == "render":
            return node
        if isinstance(node.func, ast.Attribute) and node.func.attr == "render":
            return node
        return None

    def _extract_render_call_context(
        self,
        call: ast.Call,
        *,
        mapping_alias_keys: dict[str, set[str]],
    ) -> tuple[str | None, set[str]]:
        template_node = self._get_call_arg(call, keyword="template_name", index=1)
        context_node = self._get_call_arg(call, keyword="context", index=2)

        template_name = self._get_string_constant(template_node)
        context_keys = self._extract_keys_from_mapping_expression(
            context_node,
            mapping_alias_keys=mapping_alias_keys,
        )
        return template_name, context_keys

    def _get_call_arg(
        self, call: ast.Call, *, keyword: str, index: int
    ) -> ast.AST | None:
        for kw in call.keywords:
            if kw.arg == keyword:
                return kw.value
        if len(call.args) > index:
            return call.args[index]
        return None

    def _extract_keys_from_method(
        self, method: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> set[str]:
        aliases = {"context"}
        mapping_alias_keys: dict[str, set[str]] = {}
        keys: set[str] = set()

        for statement in method.body:
            if isinstance(statement, ast.Assign):
                keys.update(
                    self._extract_keys_from_assignment(
                        statement,
                        aliases,
                        mapping_alias_keys,
                    )
                )
                self._update_aliases_from_assignment(
                    statement,
                    aliases,
                    mapping_alias_keys,
                )
            elif isinstance(statement, ast.AnnAssign):
                keys.update(
                    self._extract_keys_from_ann_assignment(
                        statement,
                        aliases,
                        mapping_alias_keys,
                    )
                )
                self._update_aliases_from_ann_assignment(
                    statement,
                    aliases,
                    mapping_alias_keys,
                )
            elif isinstance(statement, ast.AugAssign):
                keys.update(
                    self._extract_keys_from_aug_assignment(
                        statement,
                        aliases,
                        mapping_alias_keys,
                    )
                )
            elif isinstance(statement, ast.Expr):
                keys.update(
                    self._extract_keys_from_expression(
                        statement.value,
                        aliases,
                        mapping_alias_keys,
                    )
                )
            elif isinstance(statement, ast.Return):
                keys.update(
                    self._extract_keys_from_return(
                        statement.value,
                        aliases,
                        mapping_alias_keys,
                    )
                )
        return keys

    def _extract_keys_from_assignment(
        self,
        node: ast.Assign,
        aliases: set[str],
        mapping_alias_keys: dict[str, set[str]],
    ) -> set[str]:
        keys: set[str] = set()
        for target in node.targets:
            keys.update(self._extract_key_from_subscript_target(target, aliases))
            if isinstance(target, ast.Name):
                keys.update(
                    self._extract_keys_from_mapping_expression(
                        node.value,
                        aliases=aliases,
                        mapping_alias_keys=mapping_alias_keys,
                    )
                )
        return keys

    def _extract_keys_from_ann_assignment(
        self,
        node: ast.AnnAssign,
        aliases: set[str],
        mapping_alias_keys: dict[str, set[str]],
    ) -> set[str]:
        keys = set(self._extract_key_from_subscript_target(node.target, aliases))
        if isinstance(node.target, ast.Name):
            keys.update(
                self._extract_keys_from_mapping_expression(
                    node.value,
                    aliases=aliases,
                    mapping_alias_keys=mapping_alias_keys,
                )
            )
        return keys

    def _extract_keys_from_aug_assignment(
        self,
        node: ast.AugAssign,
        aliases: set[str],
        mapping_alias_keys: dict[str, set[str]],
    ) -> set[str]:
        if (
            isinstance(node.op, ast.BitOr)
            and isinstance(node.target, ast.Name)
            and node.target.id in aliases
        ):
            return self._extract_keys_from_mapping_expression(
                node.value,
                aliases=aliases,
                mapping_alias_keys=mapping_alias_keys,
            )
        return set()

    def _extract_keys_from_expression(
        self,
        node: ast.AST,
        aliases: set[str],
        mapping_alias_keys: dict[str, set[str]],
    ) -> set[str]:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in aliases
        ):
            keys = set()
            if node.args:
                keys.update(
                    self._extract_keys_from_mapping_expression(
                        node.args[0],
                        aliases=aliases,
                        mapping_alias_keys=mapping_alias_keys,
                    )
                )
            for keyword in node.keywords:
                if keyword.arg:
                    keys.add(keyword.arg)
            return keys
        return set()

    def _extract_keys_from_return(
        self,
        node: ast.AST | None,
        aliases: set[str],
        mapping_alias_keys: dict[str, set[str]],
    ) -> set[str]:
        if node is None:
            return set()
        return self._extract_keys_from_mapping_expression(
            node,
            aliases=aliases,
            mapping_alias_keys=mapping_alias_keys,
        )

    def _extract_key_from_subscript_target(
        self, target: ast.AST, aliases: set[str]
    ) -> set[str]:
        if (
            isinstance(target, ast.Subscript)
            and isinstance(target.value, ast.Name)
            and target.value.id in aliases
        ):
            key = self._get_string_constant(target.slice)
            if key:
                return {key}
        return set()

    def _extract_keys_from_mapping_expression(
        self,
        node: ast.AST | None,
        aliases: set[str] | None = None,
        mapping_alias_keys: dict[str, set[str]] | None = None,
    ) -> set[str]:
        if node is None:
            return set()

        if isinstance(node, ast.Dict):
            return self._extract_keys_from_dict(
                node,
                aliases=aliases,
                mapping_alias_keys=mapping_alias_keys,
            )

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self._extract_keys_from_mapping_expression(
                node.left,
                aliases=aliases,
                mapping_alias_keys=mapping_alias_keys,
            ) | self._extract_keys_from_mapping_expression(
                node.right,
                aliases=aliases,
                mapping_alias_keys=mapping_alias_keys,
            )

        if aliases and isinstance(node, ast.Name) and node.id in aliases:
            return set()

        if mapping_alias_keys and isinstance(node, ast.Name):
            return set(mapping_alias_keys.get(node.id, set()))

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _CONTEXT_METHOD_NAMES
        ):
            return set()

        return set()

    def _extract_keys_from_dict(
        self,
        node: ast.Dict,
        aliases: set[str] | None = None,
        mapping_alias_keys: dict[str, set[str]] | None = None,
    ) -> set[str]:
        keys = set()
        for key, value in zip(node.keys, node.values):
            if key is None:
                keys.update(
                    self._extract_keys_from_mapping_expression(
                        value,
                        aliases=aliases,
                        mapping_alias_keys=mapping_alias_keys,
                    )
                )
                continue
            string_key = self._get_string_constant(key)
            if string_key:
                keys.add(string_key)
        return keys

    def _update_aliases_from_assignment(
        self,
        node: ast.Assign,
        aliases: set[str],
        mapping_alias_keys: dict[str, set[str]],
    ) -> None:
        for target in node.targets:
            self._update_aliases_from_target_value(
                target,
                node.value,
                aliases,
                mapping_alias_keys,
            )

    def _update_aliases_from_ann_assignment(
        self,
        node: ast.AnnAssign,
        aliases: set[str],
        mapping_alias_keys: dict[str, set[str]],
    ) -> None:
        self._update_aliases_from_target_value(
            node.target,
            node.value,
            aliases,
            mapping_alias_keys,
        )

    def _update_mapping_aliases_from_assignment(
        self,
        node: ast.Assign,
        mapping_alias_keys: dict[str, set[str]],
    ) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                mapping_alias_keys[target.id] = (
                    self._extract_keys_from_mapping_expression(
                        node.value,
                        mapping_alias_keys=mapping_alias_keys,
                    )
                )

    def _update_mapping_aliases_from_ann_assignment(
        self,
        node: ast.AnnAssign,
        mapping_alias_keys: dict[str, set[str]],
    ) -> None:
        if isinstance(node.target, ast.Name):
            mapping_alias_keys[node.target.id] = (
                self._extract_keys_from_mapping_expression(
                    node.value,
                    mapping_alias_keys=mapping_alias_keys,
                )
            )

    def _update_aliases_from_target_value(
        self,
        target: ast.AST,
        value: ast.AST | None,
        aliases: set[str],
        mapping_alias_keys: dict[str, set[str]],
    ) -> None:
        if not isinstance(target, ast.Name) or value is None:
            return

        mapping_alias_keys[target.id] = self._extract_keys_from_mapping_expression(
            value,
            aliases=aliases,
            mapping_alias_keys=mapping_alias_keys,
        )

        if self._is_context_base_call(value):
            aliases.add(target.id)
            return

        if isinstance(value, ast.Name) and value.id in aliases:
            aliases.add(target.id)

    def _is_context_base_call(self, node: ast.AST) -> bool:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _CONTEXT_METHOD_NAMES
        ):
            return True
        return False

    def _get_string_constant(self, node: ast.AST | None) -> str | None:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None
