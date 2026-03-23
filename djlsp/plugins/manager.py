import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from lsprotocol.types import CompletionItem

from djlsp.plugins.base import PLUGIN_API_VERSION, Plugin, PluginContext

logger = logging.getLogger(__name__)


class PluginManager:
    def __init__(
        self,
        *,
        plugins: list[Plugin] | None = None,
        hook_timeout_ms: int = 200,
        max_failures: int = 3,
    ):
        self.plugins: dict[str, Plugin] = {}
        self.hook_timeout_ms = hook_timeout_ms
        self.max_failures = max_failures
        self.enabled_overrides: set[str] | None = None
        self.disabled_plugins: set[str] = set()
        self.settings: dict[str, dict] = {}
        self.failure_count: dict[str, int] = {}

        for plugin in plugins or []:
            self.register(plugin)

    def register(self, plugin: Plugin):
        if not plugin.name:
            raise ValueError("Plugin must define a non-empty name")
        self.plugins[plugin.name] = plugin
        self.failure_count.setdefault(plugin.name, 0)

    def configure(self, *, options: dict | None = None):
        options = options or {}
        enabled = options.get("enabled")
        self.enabled_overrides = set(enabled) if isinstance(enabled, list) else None
        disabled = options.get("disabled")
        self.disabled_plugins = set(disabled) if isinstance(disabled, list) else set()
        settings = options.get("settings")
        self.settings = settings if isinstance(settings, dict) else {}
        timeout_ms = options.get("hook_timeout_ms")
        if isinstance(timeout_ms, int) and timeout_ms > 0:
            self.hook_timeout_ms = timeout_ms

    def _is_enabled(self, plugin: Plugin) -> bool:
        if plugin.name in self.disabled_plugins:
            return False
        if (
            self.enabled_overrides is not None
            and plugin.name not in self.enabled_overrides
        ):
            return False
        return plugin.default_enabled

    def _is_compatible(self, plugin: Plugin) -> bool:
        return plugin.api_version == PLUGIN_API_VERSION

    def _active_plugins(self) -> list[Plugin]:
        active = []
        for plugin in self.plugins.values():
            if not self._is_compatible(plugin):
                logger.warning(
                    "Plugin %s has unsupported api version %s",
                    plugin.name,
                    plugin.api_version,
                )
                continue
            if self._is_enabled(plugin):
                active.append(plugin)
        return sorted(active, key=lambda plugin: plugin.priority)

    def _plugin_context(
        self, plugin: Plugin, base_context: PluginContext
    ) -> PluginContext:
        return PluginContext(
            workspace_index=base_context.workspace_index,
            jedi_project=base_context.jedi_project,
            document=base_context.document,
            settings=self.settings.get(plugin.name, {}),
        )

    def _run_with_guard(self, plugin: Plugin, hook_name: str, fn, default):
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fn)
                return future.result(timeout=self.hook_timeout_ms / 1000)
        except TimeoutError:
            logger.error(
                "Plugin %s hook %s timed out after %sms",
                plugin.name,
                hook_name,
                self.hook_timeout_ms,
            )
        except Exception:
            logger.exception("Plugin %s hook %s failed", plugin.name, hook_name)

        self.failure_count[plugin.name] = self.failure_count.get(plugin.name, 0) + 1
        if self.failure_count[plugin.name] >= self.max_failures:
            logger.error("Disabling misbehaving plugin for session: %s", plugin.name)
            self.disabled_plugins.add(plugin.name)
        return default

    def completions(
        self, context: PluginContext, *, line: int, character: int
    ) -> list[CompletionItem]:
        merged: list[CompletionItem] = []
        seen: set[tuple] = set()
        for plugin in self._active_plugins():
            plugin_context = self._plugin_context(plugin, context)
            items = self._run_with_guard(
                plugin,
                "on_completions",
                lambda plugin=plugin, plugin_context=plugin_context: (
                    plugin.on_completions(
                        plugin_context,
                        line=line,
                        character=character,
                    )
                ),
                [],
            )
            for item in items:
                key = (item.label, item.kind, item.detail, item.documentation)
                if key in seen:
                    continue
                seen.add(key)
                merged.append(item)
        return merged

    def hover(self, context: PluginContext, *, line: int, character: int):
        for plugin in self._active_plugins():
            plugin_context = self._plugin_context(plugin, context)
            hover = self._run_with_guard(
                plugin,
                "on_hover",
                lambda plugin=plugin, plugin_context=plugin_context: plugin.on_hover(
                    plugin_context,
                    line=line,
                    character=character,
                ),
                None,
            )
            if hover is not None:
                return hover
        return None

    def definition(self, context: PluginContext, *, line: int, character: int):
        for plugin in self._active_plugins():
            plugin_context = self._plugin_context(plugin, context)
            definition = self._run_with_guard(
                plugin,
                "on_definition",
                lambda plugin=plugin, plugin_context=plugin_context: (
                    plugin.on_definition(
                        plugin_context,
                        line=line,
                        character=character,
                    )
                ),
                None,
            )
            if definition is not None:
                return definition
        return None

    def resolve_completion(self, item: CompletionItem) -> CompletionItem:
        for plugin in self._active_plugins():
            resolved = self._run_with_guard(
                plugin,
                "on_completion_resolve",
                lambda plugin=plugin: plugin.on_completion_resolve(item),
                None,
            )
            if resolved is not None:
                return resolved
        return item
