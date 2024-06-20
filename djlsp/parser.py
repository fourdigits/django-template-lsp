import logging
import re
from functools import cached_property
from re import Match

from lsprotocol.types import CompletionItem, Hover
from pygls.workspace import TextDocument

from djlsp.constants import BUILTIN
from djlsp.index import WorkspaceIndex

logger = logging.getLogger(__name__)


class TemplateParser:

    def __init__(self, workspace_index: WorkspaceIndex, document: TextDocument):
        self.workspace_index: WorkspaceIndex = workspace_index
        self.document: TextDocument = document

    @cached_property
    def loaded_libraries(self):
        re_loaded = re.compile(r".*{% ?load ([\w ]*) ?%}$")
        loaded = {BUILTIN}
        for line in self.document.lines:
            if match := re_loaded.match(line):
                loaded.update(
                    [
                        lib
                        for lib in match.group(1).strip().split(" ")
                        if lib in self.workspace_index.libraries
                    ]
                )
        logger.debug(f"Loaded libraries: {loaded}")
        return loaded

    ###################################################################################
    # Completions
    ###################################################################################
    def completions(self, line, character):
        line_fragment = self.document.lines[line][:character]
        matchers = [
            (re.compile(r".*{% ?load ([\w ]*)$"), self.get_load_completions),
            (re.compile(r".*{% ?block ([\w]*)$"), self.get_block_completions),
            (re.compile(r""".*{% ?url ('|")([\w\-:]*)$"""), self.get_url_completions),
            (
                re.compile(r".*{% ?static ('|\")([\w\-\.\/]*)$"),
                self.get_static_completions,
            ),
            (
                re.compile(r""".*{% ?(extends|include) ('|")([\w\-:]*)$"""),
                self.get_template_completions,
            ),
            (re.compile(r"^.*{% ?(\w*)$"), self.get_tag_completions),
            (
                re.compile(r"^.*({%|{{) ?[\w \.\|]*\|(\w*)$"),
                self.get_filter_completions,
            ),
            (
                re.compile(r".*({{|{% \w+).* ([\w\d_\.]*)$"),
                self.get_context_completions,
            ),
        ]

        for regex, completion in matchers:
            if match := regex.match(line_fragment):
                return completion(match)
        return []

    def get_load_completions(self, match: Match):
        prefix = match.group(1).split(" ")[-1]
        logger.debug(f"Find load matches for: {prefix}")
        return [
            CompletionItem(label=lib)
            for lib in self.workspace_index.libraries.keys()
            if lib != BUILTIN and lib.startswith(prefix)
        ]

    def get_block_completions(self, match: Match):
        prefix = match.group(1).strip()
        logger.debug(f"Find block matches for: {prefix}")
        block_names = []
        if "/templates/" in self.document.path:
            template_name = self.document.path.split("/templates/", 1)[1]
            if template := self.workspace_index.templates.get(template_name):
                block_names = self._recursive_block_names(template.extends)

        used_block_names = []
        re_block = re.compile(r"{% ?block ([\w]*) ?%}")
        for line in self.document.lines:
            if matches := re_block.findall(line):
                used_block_names.extend(matches)

        return [
            CompletionItem(label=name)
            for name in block_names
            if name not in used_block_names and name.startswith(prefix)
        ]

    def _recursive_block_names(self, template_name, looked_up_templates=None):
        looked_up_templates = looked_up_templates if looked_up_templates else []
        looked_up_templates.append(template_name)

        block_names = []
        if template := self.workspace_index.templates.get(template_name):
            block_names.extend(template.blocks)
            if template.extends and template.extends not in looked_up_templates:
                block_names.extend(
                    self._recursive_block_names(template.extends, looked_up_templates)
                )
        return list(set(block_names))

    def get_static_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find static matches for: {prefix}")
        return [
            CompletionItem(label=static_file)
            for static_file in self.workspace_index.static_files
            if static_file.startswith(prefix)
        ]

    def get_url_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find url matches for: {prefix}")
        return [
            CompletionItem(label=url)
            for url in self.workspace_index.urls
            if url.startswith(prefix)
        ]

    def get_template_completions(self, match: Match):
        prefix = match.group(3)
        logger.debug(f"Find {match.group(1)} matches for: {prefix}")
        return [
            CompletionItem(label=template)
            for template in self.workspace_index.templates
            if template.startswith(prefix)
        ]

    def get_tag_completions(self, match: Match):
        prefix = match.group(1)
        logger.debug(f"Find tag matches for: {prefix}")

        tags = []
        for lib_name in self.loaded_libraries:
            if lib := self.workspace_index.libraries.get(lib_name):
                for tag in lib.tags.values():
                    tags.append(
                        CompletionItem(
                            label=tag.name,
                            documentation=tag.docs,
                        )
                    )
                    # TODO: Only add inner/clossing if there is opening tag
                    tags.extend([CompletionItem(label=tag) for tag in tag.inner_tags])
                    if tag.closing_tag:
                        tags.append(CompletionItem(label=tag.closing_tag))

        return [tag for tag in tags if tag.label.startswith(prefix)]

    def get_filter_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find filter matches for: {prefix}")
        filters = []
        for lib_name in self.loaded_libraries:
            if lib := self.workspace_index.libraries.get(lib_name):
                filters.extend(
                    [
                        CompletionItem(
                            label=filt.name,
                            documentation=filt.docs,
                        )
                        for filt in lib.filters.values()
                    ]
                )
        return [
            filter_name
            for filter_name in filters
            if filter_name.label.startswith(prefix)
        ]

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

        return [
            CompletionItem(label=var)
            for var in lookup_context
            if var.startswith(prefix)
        ]

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

    ###################################################################################
    # Hover
    ###################################################################################
    def hover(self, line, character):
        line_fragment = self.document.lines[line][:character]
        matchers = [
            (re.compile(r"^.*({%|{{) ?[\w \.\|]*\|(\w*)$"), self.get_filter_hover),
            (re.compile(r"^.*{% ?(\w*)$"), self.get_tag_hover),
        ]
        for regex, hover in matchers:
            if match := regex.match(line_fragment):
                return hover(line, character, match)
        return None

    def get_filter_hover(self, line, character, match: Match):
        filter_name = self._get_full_hover_name(line, character, match.group(2))
        logger.debug(f"Find filter hover for: {filter_name}")
        for lib in self.workspace_index.libraries.values():
            if lib.name in self.loaded_libraries and filter_name in lib.filters:
                return Hover(
                    contents=lib.filters[filter_name].docs,
                )
        return None

    def get_tag_hover(self, line, character, match: Match):
        tag_name = self._get_full_hover_name(line, character, match.group(1))
        logger.debug(f"Find tag hover for: {tag_name}")
        for lib in self.workspace_index.libraries.values():
            if lib.name in self.loaded_libraries and tag_name in lib.tags:
                return Hover(
                    contents=lib.tags[tag_name].docs,
                )
        return None

    def _get_full_hover_name(self, line, character, first_part):
        if match_after := re.match(
            r"^([\w\d]+).*", self.document.lines[line][character:]
        ):
            return first_part + match_after.group(1)
        return first_part
