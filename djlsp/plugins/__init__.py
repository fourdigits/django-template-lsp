from __future__ import annotations

import logging
from functools import cache
from importlib.metadata import entry_points

logger = logging.getLogger(__name__)

COLLECTOR_PLUGINS_GROUP = "djlsp.collector_plugins"
PARSER_PLUGINS_GROUP = "djlsp.parser_plugins"
CONTEXT_PLUGINS_GROUP = "djlsp.context_plugins"


@cache
def _load_entry_points(group: str) -> list:
    plugins = []
    for ep in entry_points(group=group):
        try:
            plugins.append(ep.load())
        except Exception:
            logger.warning(
                "Failed to load plugin %r from group %r", ep.name, group, exc_info=True
            )
    return plugins


def get_parser_plugin_classes() -> list:
    """Return cached list of parser plugin classes (djlsp.parser_plugins)."""
    return _load_entry_points(PARSER_PLUGINS_GROUP)


def get_context_plugin_classes() -> list:
    """Return cached list of context plugin classes (djlsp.context_plugins)."""
    return _load_entry_points(CONTEXT_PLUGINS_GROUP)


class CollectorPlugin:
    """Base class for collector plugins.

    Collector plugins run inside the Django subprocess (django-collector.py)
    and can modify or extend the data collected from the Django project.

    Register via entry points in pyproject.toml::

        [project.entry-points."djlsp.collector_plugins"]
        myplugin = "mypackage.plugin:MyCollectorPlugin"
    """

    def collect(self, collector) -> None:
        """Called after standard collection completes.

        Args:
            collector: ``DjangoIndexCollector`` instance with the following
                mutable attributes:

                - ``templates`` – ``dict[str, dict]`` keyed by template name
                - ``urls`` – ``dict[str, dict]`` keyed by URL name
                - ``libraries`` – ``dict[str, dict]`` keyed by library name
                - ``static_files`` – ``list[str]``
                - ``global_template_context`` – ``dict[str, str | None]``
                - ``file_watcher_globs`` – ``list[str]``
                - ``plugin_data`` – ``dict`` for arbitrary custom data

        Use ``collector.plugin_data`` to store custom data that should be
        available to parser and context plugins via
        ``self.workspace_index.plugin_data``.
        """
        pass


class ParserPlugin:
    """Base class for parser plugins.

    Parser plugins run in the LSP server process and can extend completions,
    hover information, and goto-definition for template files.

    Register via entry points in pyproject.toml::

        [project.entry-points."djlsp.parser_plugins"]
        myplugin = "mypackage.plugin:MyParserPlugin"
    """

    def __init__(self, workspace_index, jedi_project, document):
        self.workspace_index = workspace_index
        self.jedi_project = jedi_project
        self.document = document

    def completions(self, line: int, character: int) -> list:
        """Return additional ``CompletionItem`` objects for the given position.

        Called when the built-in matchers produce no results.
        """
        return []

    def hover(self, line: int, character: int):
        """Return a ``Hover`` object for the given position, or ``None``.

        Called when the built-in matchers produce no results.
        """
        return None

    def goto_definition(self, line: int, character: int):
        """Return a ``Location`` object for goto-definition, or ``None``.

        Called when the built-in matchers produce no results.
        """
        return None


class ContextPlugin:
    """Base class for context plugins.

    Context plugins run in the LSP server process and can add template context
    variables to supplement those found during data collection.

    Register via entry points in pyproject.toml::

        [project.entry-points."djlsp.context_plugins"]
        myplugin = "mypackage.plugin:MyContextPlugin"
    """

    def __init__(self, workspace_index, jedi_project, document):
        self.workspace_index = workspace_index
        self.jedi_project = jedi_project
        self.document = document

    def get_context(self, *, line: int, character: int, context: dict) -> dict:
        """Return additional context variables as a ``dict[str, Variable]``.

        Args:
            line: Current cursor line.
            character: Current cursor character.
            context: Already-assembled context from the workspace index and
                built-in resolution. Do not mutate this dict; return new
                entries instead. If two plugins set the same key, the last
                one wins.

        Returns:
            ``dict`` mapping variable names to ``Variable`` instances (from
            ``djlsp.index``).
        """
        return {}
