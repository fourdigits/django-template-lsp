import logging
import re
from functools import cached_property
from re import Match

from pygls.workspace import TextDocument

from djlsp.constants import BUILTIN
from djlsp.index import WorkspaceIndex

logger = logging.getLogger(__name__)


class TemplateParser:
    re_loaded = re.compile(r".*{% ?load ([\w ]*) ?%}$")
    re_load = re.compile(r".*{% ?load ([\w ]*)$")
    re_url = re.compile(r""".*{% ?url ('|")([\w\-:]*)$""")
    re_static = re.compile(r".*{% ?static ('|\")([\w\-\.\/]*)$")
    re_tag = re.compile(r"^.*{% ?(\w*)$")
    re_filter = re.compile(r"^.*({%|{{) ?[\w \.\|]*\|(\w*)$")
    re_template = re.compile(r""".*{% ?(extends|include) ('|")([\w\-:]*)$""")
    re_context = re.compile(r".*({{|{% \w+).* ([\w\d_\.]*)$")

    def __init__(self, workspace_index: WorkspaceIndex, document: TextDocument):
        self.workspace_index: WorkspaceIndex = workspace_index
        self.document: TextDocument = document

    @cached_property
    def loaded_libraries(self):
        loaded = {BUILTIN}
        for line in self.document.lines:
            if match := self.re_loaded.match(line):
                loaded.update(
                    [
                        lib
                        for lib in match.group(1).strip().split(" ")
                        if lib in self.workspace_index.libraries
                    ]
                )
        logger.debug(f"Loaded libraries: {loaded}")
        return loaded

    def completions(self, line, character):
        line_fragment = self.document.lines[line][:character]
        try:
            if match := self.re_load.match(line_fragment):
                return self.get_load_completions(match)
            if match := self.re_url.match(line_fragment):
                return self.get_url_completions(match)
            elif match := self.re_static.match(line_fragment):
                return self.get_static_completions(match)
            elif match := self.re_template.match(line_fragment):
                return self.get_template_completions(match)
            elif match := self.re_tag.match(line_fragment):
                return self.get_tag_completions(match)
            elif match := self.re_filter.match(line_fragment):
                return self.get_filter_completions(match)
            elif match := self.re_context.match(line_fragment):
                return self.get_context_completions(match)
        except Exception as e:
            logger.debug(e)

        return []

    def get_load_completions(self, match: Match):
        prefix = match.group(1).split(" ")[-1]
        logger.debug(f"Find load matches for: {prefix}")
        return sorted(
            [
                lib
                for lib in self.workspace_index.libraries.keys()
                if lib != BUILTIN and lib.startswith(prefix)
            ]
        )

    def get_static_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find static matches for: {prefix}")
        return sorted(
            [
                static_file
                for static_file in self.workspace_index.static_files
                if static_file.startswith(prefix)
            ]
        )

    def get_url_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find url matches for: {prefix}")
        return sorted(
            [url for url in self.workspace_index.urls if url.startswith(prefix)]
        )

    def get_template_completions(self, match: Match):
        prefix = match.group(3)
        logger.debug(f"Find {match.group(1)} matches for: {prefix}")
        return sorted(
            [
                template
                for template in self.workspace_index.templates
                if template.startswith(prefix)
            ]
        )

    def get_tag_completions(self, match: Match):
        prefix = match.group(1)
        logger.debug(f"Find tag matches for: {prefix}")

        tags = []
        for lib_name in self.loaded_libraries:
            if lib := self.workspace_index.libraries.get(lib_name):
                for tag in lib.tags.values():
                    tags.append(tag.name)
                    # TODO: Only add inner/clossing if there is opening tag
                    tags.extend(tag.inner_tags)
                    if tag.closing_tag:
                        tags.append(tag.closing_tag)

        return sorted([tag for tag in tags if tag.startswith(prefix)])

    def get_filter_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find filter matches for: {prefix}")
        filters = []
        for lib_name in self.loaded_libraries:
            if lib := self.workspace_index.libraries.get(lib_name):
                filters.extend(lib.filters)
        return sorted(
            [filter_name for filter_name in filters if filter_name.startswith(prefix)]
        )

    def get_context_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find context matches for: {prefix}")
        context = self.workspace_index.global_template_context.copy()
        if "/templates/" in self.document.path:
            template_name = self.document.path.split("/templates/", 1)[1]
            if template := self.workspace_index.templates.get(template_name):
                context.update(template.context)

        prefix, lookup_context = self._recursive_context_lookup(
            prefix.strip().split("."), context
        )

        return [var for var in lookup_context if var.startswith(prefix)]

    def _recursive_context_lookup(self, parts: [str], context: dict[str, str]):
        if len(parts) == 1:
            return parts[0], context

        variable, *parts = parts

        # Get new context
        if variable_type := context.get(variable):
            if new_context := self.workspace_index.object_types.get(variable_type):
                return self._recursive_context_lookup(parts, new_context)

        # No suggesions found
        return "", []
