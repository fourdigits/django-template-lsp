import ast
import inspect
import logging
import textwrap

logger = logging.getLogger(__name__)

_CONTEXT_METHOD_NAMES = {"get_context_data", "get_context"}


class AstContextCollector:
    def extract_context_keys(self, view: type) -> set[str]:
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

    def _find_class_node(self, tree: ast.Module, name: str) -> ast.ClassDef | None:
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == name:
                return node
        return None

    def _extract_keys_from_method(
        self, method: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> set[str]:
        aliases = {"context"}
        keys: set[str] = set()

        for statement in ast.walk(method):
            if isinstance(statement, ast.Assign):
                keys.update(self._extract_keys_from_assignment(statement, aliases))
                self._update_aliases_from_assignment(statement, aliases)
            elif isinstance(statement, ast.AnnAssign):
                keys.update(self._extract_keys_from_ann_assignment(statement, aliases))
                self._update_aliases_from_ann_assignment(statement, aliases)
            elif isinstance(statement, ast.AugAssign):
                keys.update(self._extract_keys_from_aug_assignment(statement, aliases))
            elif isinstance(statement, ast.Expr):
                keys.update(
                    self._extract_keys_from_expression(statement.value, aliases)
                )
            elif isinstance(statement, ast.Return):
                keys.update(self._extract_keys_from_return(statement.value, aliases))
        return keys

    def _extract_keys_from_assignment(
        self, node: ast.Assign, aliases: set[str]
    ) -> set[str]:
        keys: set[str] = set()
        for target in node.targets:
            keys.update(self._extract_key_from_subscript_target(target, aliases))
        return keys

    def _extract_keys_from_ann_assignment(
        self, node: ast.AnnAssign, aliases: set[str]
    ) -> set[str]:
        return self._extract_key_from_subscript_target(node.target, aliases)

    def _extract_keys_from_aug_assignment(
        self, node: ast.AugAssign, aliases: set[str]
    ) -> set[str]:
        if (
            isinstance(node.op, ast.BitOr)
            and isinstance(node.target, ast.Name)
            and node.target.id in aliases
        ):
            return self._extract_keys_from_mapping_expression(node.value)
        return set()

    def _extract_keys_from_expression(
        self, node: ast.AST, aliases: set[str]
    ) -> set[str]:
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "update"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in aliases
            and node.args
        ):
            return self._extract_keys_from_mapping_expression(node.args[0])
        return set()

    def _extract_keys_from_return(
        self, node: ast.AST | None, aliases: set[str]
    ) -> set[str]:
        if node is None:
            return set()
        return self._extract_keys_from_mapping_expression(node, aliases=aliases)

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
        self, node: ast.AST, aliases: set[str] | None = None
    ) -> set[str]:
        if isinstance(node, ast.Dict):
            return self._extract_keys_from_dict(node)

        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            return self._extract_keys_from_mapping_expression(
                node.left, aliases=aliases
            ) | self._extract_keys_from_mapping_expression(node.right, aliases=aliases)

        if aliases and isinstance(node, ast.Name) and node.id in aliases:
            return set()

        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _CONTEXT_METHOD_NAMES
        ):
            return set()

        return set()

    def _extract_keys_from_dict(self, node: ast.Dict) -> set[str]:
        keys = set()
        for key in node.keys:
            string_key = self._get_string_constant(key)
            if string_key:
                keys.add(string_key)
        return keys

    def _update_aliases_from_assignment(
        self, node: ast.Assign, aliases: set[str]
    ) -> None:
        for target in node.targets:
            self._update_aliases_from_target_value(target, node.value, aliases)

    def _update_aliases_from_ann_assignment(
        self, node: ast.AnnAssign, aliases: set[str]
    ) -> None:
        self._update_aliases_from_target_value(node.target, node.value, aliases)

    def _update_aliases_from_target_value(
        self, target: ast.AST, value: ast.AST | None, aliases: set[str]
    ) -> None:
        if not isinstance(target, ast.Name) or value is None:
            return

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
