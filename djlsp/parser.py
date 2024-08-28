import logging
import re
from functools import cached_property
from re import Match
from textwrap import dedent

import jedi
from lsprotocol.types import CompletionItem, Hover, Location, Position, Range
from pygls.workspace import TextDocument

from djlsp.constants import BUILTIN
from djlsp.index import WorkspaceIndex

logger = logging.getLogger(__name__)


class TemplateParser:

    def __init__(
        self,
        workspace_index: WorkspaceIndex,
        jedi_project: jedi.Project,
        document: TextDocument,
    ):
        self.workspace_index: WorkspaceIndex = workspace_index
        self.jedi_project: jedi.Project = jedi_project
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

    @cached_property
    def context(self):
        context = self.workspace_index.global_template_context.copy()
        if "/templates/" in self.document.path:
            template_name = self.document.path.split("/templates/", 1)[1]
            if template := self.workspace_index.templates.get(template_name):
                context.update(template.context)

        # Add all variables found in template to context
        # TODO: Use scope to only add to context based on cursor position
        re_as = re.compile(r".*{%.*as ([\w ]+) %}.*$")
        re_for = re.compile(r".*{% ?for ([\w ,]*) in.*$")
        re_with = re.compile(r".*{% ?with (.+) ?%}.*")
        found_variables = []
        for line in self.document.lines:
            if match := re_as.match(line):
                found_variables.extend(match.group(1).split(" "))
            if match := re_for.match(line):
                context["forloop"] = None
                found_variables.extend(match.group(1).split(","))
            if match := re_with.match(line):
                for assignment in match.group(1).split(" "):
                    split_assignment = assignment.split("=")
                    if len(split_assignment) == 2:
                        found_variables.append(split_assignment[0])

        for variable in found_variables:
            if variable_stripped := variable.strip():
                context[variable_stripped] = None

        # Update type definations based on template type comments
        # only simple version of variable: full python path:
        # {# type some_variable: full.python.path.to.class #}
        re_type = re.compile(r".*{# type (\w+) ?: ?([\w\d_\.]+) ?#}.*")
        for line in self.document.lines:
            if match := re_type.match(line):
                variable = match.group(1)
                variable_type = match.group(2)
                context[variable] = variable_type

        return context

    def create_jedi_script(self, code) -> jedi.Script:
        """
        Generate jedi Script based on template context and given code.
        """
        script_lines = []
        if re.search(r"{% ?for ", self.document.source):
            # TODO: Only add in for scope
            script_lines.append(
                dedent(
                    """
                    class DummyForLoop:
                        counter: int
                        counter0: int
                        revcounter: int
                        revcounter0: int
                        first: bool
                        last: bool
                        parentloop: "DummyForLoop"
                    forloop: DummyForLoop
                    """
                )
            )
        for variable, variable_type in self.context.items():
            if variable_type:
                variable_import = ".".join(variable_type.split(".")[:-1])
                script_lines.extend(
                    [
                        f"import {variable_import}",
                        f"{variable}: {variable_type}",
                    ]
                )
            else:
                script_lines.append(f"{variable} = None")

        # Add user code
        script_lines.append(code)

        return jedi.Script(code="\n".join(script_lines), project=self.jedi_project)

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
                re.compile(r"^.*({%|{{).*?\|(\w*)$"),
                self.get_filter_completions,
            ),
            (
                re.compile(r"^.*{# type \w+ ?: ?([\w\d_\.]*)$"),
                self.get_type_comment_complations,
            ),
            (
                re.compile(r".*({{|{% \w+ ).*?([\w\d_\.]*)$"),
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

    def get_type_comment_complations(self, match: Match):
        prefix = match.group(1)
        logger.debug(f"Find type comment matches for: {prefix}")

        if "." in prefix:
            from_part = ".".join(prefix.split(".")[:-1])
            import_part = prefix.split(".")[-1]
            code = f"from {from_part} import {import_part}"
        else:
            code = f"import {prefix}"

        return [
            CompletionItem(label=comp.name)
            for comp in self.create_jedi_script(code).complete()
        ]

    def get_context_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find context matches for: {prefix}")

        if "." in prefix:
            # Find . completions with Jedi
            return [
                CompletionItem(label=comp.name)
                for comp in self.create_jedi_script(prefix).complete()
                # Functions are ignored since Django templates do not allow
                # passing arguments to them.
                if comp.type != "function" and not comp.name.startswith("__")
            ]
        else:
            # Only context completions
            return [
                CompletionItem(label=var)
                for var in self.context
                if var.startswith(prefix)
            ]

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

    ###################################################################################
    # Goto definition
    ###################################################################################
    def goto_definition(self, line, character):
        line_fragment = self.document.lines[line][:character]
        matchers = [
            (
                re.compile(r""".*{% ?(extends|include) ('|")([\w\-\./]*)$"""),
                self.get_template_definition,
            ),
            (re.compile(r"^.*{% ?(\w*)$"), self.get_tag_definition),
            (re.compile(r"^.*({%|{{).*?\|(\w*)$"), self.get_filter_definition),
            (
                re.compile(r".*({{|{% \w+ ).*?([\w\d_\.]*)$"),
                self.get_context_definition,
            ),
        ]
        for regex, definition in matchers:
            if match := regex.match(line_fragment):
                return definition(line, character, match)
        return None

    def create_location(self, location, path, line):
        root_path = (
            self.workspace_index.src_path
            if location == "src"
            else self.workspace_index.env_path
        )
        return Location(
            uri=f"file://{root_path}/{path}",
            range=Range(
                start=Position(line=int(line), character=0),
                end=Position(line=int(line), character=0),
            ),
        )

    def get_template_definition(self, line, character, match: Match):
        if match_after := re.match(r'^(.*)".*', self.document.lines[line][character:]):
            template_name = match.group(3) + match_after.group(1)
            logger.debug(f"Find template goto definition for: {template_name}")
            if template := self.workspace_index.templates.get(template_name):
                location, path = template.path.split(":")
                return self.create_location(location, path, 0)

    def get_tag_definition(self, line, character, match: Match):
        full_match = self._get_full_definition_name(line, character, match.group(1))
        logger.debug(f"Find tag goto definition for: {full_match}")
        for lib in self.loaded_libraries:
            if tag := self.workspace_index.libraries[lib].tags.get(full_match):
                if tag.source:
                    return self.create_location(*tag.source.split(":"))

    def get_filter_definition(self, line, character, match: Match):
        full_match = self._get_full_definition_name(line, character, match.group(2))
        logger.debug(f"Find filter goto definition for: {full_match}")
        for lib in self.loaded_libraries:
            if filter_ := self.workspace_index.libraries[lib].filters.get(full_match):
                if filter_.source:
                    return self.create_location(*filter_.source.split(":"))

    def get_context_definition(self, line, character, match: Match):
        first_match = match.group(2)
        full_match = self._get_full_definition_name(line, character, first_match)
        logger.debug(f"Find context goto definition for: {full_match}")
        if gotos := self.create_jedi_script(full_match).goto(column=len(first_match)):
            goto = gotos[0]
            if goto.module_name == "__main__":
                # Location is in fake script get type location
                if infers := goto.infer():
                    goto = infers[0]
                else:
                    return None
            return Location(
                uri=f"file://{goto.module_path}",
                range=Range(
                    start=Position(line=goto.line, character=goto.column),
                    end=Position(line=goto.line, character=goto.column),
                ),
            )

    def _get_full_definition_name(self, line, character, first_part):
        if match_after := re.match(
            r"^([\w\d]+).*", self.document.lines[line][character:]
        ):
            return first_part + match_after.group(1)
        return first_part
