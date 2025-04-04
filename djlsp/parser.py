import hashlib
import logging
import re
import time
from functools import cached_property
from re import Match
from textwrap import dedent

import jedi
from jedi.api.classes import Completion
from lsprotocol.types import (
    CompletionItem,
    CompletionItemKind,
    Hover,
    Location,
    Position,
    Range,
)
from pygls.workspace import TextDocument

from djlsp.constants import BUILTIN
from djlsp.index import Variable, WorkspaceIndex

logger = logging.getLogger(__name__)

RE_TAGS_NO_CONTEXT = re.compile(r"{% ?(end.*|comment|csrf_token|debug|spaceless)")

_MOST_RECENT_COMPLETIONS: dict[str, Completion] = {}


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

    def get_context(self, *, line, character):
        # add global template context
        context = self.workspace_index.global_template_context.copy()
        if "/templates/" in self.document.path:
            template_name = self.document.path.split("/templates/", 1)[1]
            if template := self.workspace_index.templates.get(template_name):
                context.update(template.context)

        # Update type definations based on template type comments
        # {# type some_variable: full.python.path.to.class #}
        re_type = re.compile(r".*{# type (\w+) ?: ?(.*?) ?#}.*")
        for src_line in self.document.lines:
            if match := re_type.match(src_line):
                variable = match.group(1)
                variable_type = match.group(2)
                context[variable] = Variable(type=variable_type)

        scoped_tags = [
            (
                "for",
                re.compile(r".*{% ?for ([\w ,]*) in ([\w.]+).*$"),
                re.compile(r".*{% ?endfor"),
            ),
            (
                "with",
                re.compile(r".*{% ?with (.+) ?%}.*"),
                re.compile(r".*{% ?endwith"),
            ),
        ]
        stack = []
        for line_idx, src_line in enumerate(self.document.lines):
            # only analyze until the current line
            if line and line_idx > line:
                break

            for tag_name, re_start, re_end in scoped_tags:
                if match := re_start.match(src_line):
                    stack.append((tag_name, match))
                    break
                elif match := re_end.match(src_line):
                    found_tag, _ = stack.pop()
                    if found_tag != tag_name:
                        # TODO: show warning to user
                        logger.debug("Closing tag does not match opening")
                    break

        if stack:
            logger.debug(f"Stack not empty for {line=} {len(stack)=}:")
        for tag_name, match in stack:
            logger.debug(f"  {tag_name} {match!r} {match.groups()!r}")

            if tag_name == "for":
                context["forloop"] = Variable(type="_DjangoForLoop")
                loop_variables, variable = (
                    match.group(1).strip(),
                    match.group(2).strip(),
                )
                variable = self._django_variable_to_python(variable, context)
                if "," in loop_variables:
                    for var_idx, loop_var in enumerate(loop_variables.split(",")):
                        context[loop_var.strip()] = Variable(
                            value=f"next(iter({variable}))[{var_idx}]"
                        )
                else:
                    context[loop_variables.strip()] = Variable(
                        value=f"next(iter({variable}))"
                    )

            if tag_name == "with":
                for assignment in match.group(1).split(" "):
                    split_assignment = assignment.split("=")
                    if len(split_assignment) == 2:
                        context[split_assignment[0].strip()] = Variable(
                            value=self._django_variable_to_python(
                                split_assignment[1].strip(), context
                            )
                        )

        # As tag
        # TODO: integrate into scope matcher
        re_as = re.compile(r".*{%.*as ([\w ]+) %}.*$")
        for src_line in self.document.lines:
            if match := re_as.match(src_line):
                for variable in match.group(1).split(" "):
                    if variable_stripped := variable.strip():
                        context[variable_stripped] = Variable()

        return context

    def create_jedi_script(
        self,
        code,
        *,
        context=None,
        line=None,
        character=None,
        transform_code=True,
        execute_last_function=True,
    ) -> jedi.Script:
        """
        Generate jedi Script based on template context and given code.
        """
        if context is None:
            context = self.get_context(line=line, character=character)

        script_lines = []
        if re.search(r"{% ?for ", self.document.source):
            script_lines.append(
                dedent(
                    '''
                    class _DjangoForLoop:
                        """Django for loop context"""
                        counter: int
                        counter0: int
                        revcounter: int
                        revcounter0: int
                        first: bool
                        last: bool
                        parentloop: "_DjangoForLoop"
                    '''
                )
            )

        for variable_name, variable in context.items():
            if variable.type:
                variable_type_aliased = variable.type
                # allow to use more complex types by splitting them into segments
                # and try to import them separatly
                for imp in set(filter(None, re.split(r"\[|\]| |,", variable.type))):
                    variable_import = ".".join(imp.split(".")[:-1])
                    if variable_import == "":
                        continue

                    # create import alias to allow variable to have same name as module
                    import_alias = (
                        "__" + hashlib.md5(variable_import.encode()).hexdigest()
                    )
                    variable_type_aliased = variable_type_aliased.replace(
                        variable_import, import_alias
                    )
                    script_lines.append(f"import {variable_import} as {import_alias}")

                script_lines.append(f"{variable_name}: {variable_type_aliased}")
            else:
                script_lines.append(f"{variable_name} = {variable.value or None}")

        # Add user code
        if transform_code:
            script_lines.append(
                self._django_variable_to_python(
                    code, context, execute_last_function=execute_last_function
                )
            )
            logger.debug(
                "\n".join(["=== Jedi script ===", *script_lines, "=== End script ==="])
            )
        else:
            script_lines.append(code)

        return jedi.Script(code="\n".join(script_lines), project=self.jedi_project)

    def _django_variable_to_python(
        self, variable: str, context, *, execute_last_function=True
    ):
        def join_path(*segments: str):
            return ".".join(filter(None, segments))

        if not variable:
            return ""

        start_time = time.time()
        res = ""
        segments = variable.split(".")
        for idx, seg in enumerate(segments):
            # django uses abc.0 for list index lookup, replace those with abc[0]
            if seg.isdigit() and idx > 0:
                res = f"{res}[{seg}]"
                continue

            # django does some magic (e.g. call function automaticaly,
            # use attribute access for dictionaries, ...)
            # try to infer the correct python syntax
            infer = self.create_jedi_script(
                join_path(res, seg), context=context, transform_code=False
            ).infer()
            if not infer:
                logger.debug(
                    f"Failed to transform variable '{variable}' (got until {res})"
                )
                return variable

            # django calls functions automaticaly
            if infer[0].type == "function" and (
                execute_last_function if idx == (len(segments) - 1) else True
            ):
                res = join_path(res, seg) + "()"
            else:
                res = join_path(res, seg)

        if variable.endswith("."):
            res += "."

        total_time = time.time() - start_time
        logger.debug(
            f"Variable '{variable}' transformed to '{res}' in {total_time:.4f}s"
        )

        return res

    def _jedi_type_to_completion_kind(self, comp_type: str) -> CompletionItemKind:
        """Map Jedi completion types to LSP CompletionItemKind."""
        # https://jedi.readthedocs.io/en/latest/docs/api-classes.html#jedi.api.classes.BaseName.type
        kind_mapping = {
            "class": CompletionItemKind.Class,
            "instance": CompletionItemKind.Variable,
            "keyword": CompletionItemKind.Keyword,
            "module": CompletionItemKind.Module,
            "param": CompletionItemKind.Variable,
            "path": CompletionItemKind.File,
            "property": CompletionItemKind.Property,
            "statement": CompletionItemKind.Variable,
            "function": CompletionItemKind.Function,
        }
        return kind_mapping.get(comp_type, CompletionItemKind.Field)

    ###################################################################################
    # Completions
    ###################################################################################
    def completions(self, line, character):
        line_fragment = self.document.lines[line][:character]
        matchers = [
            (re.compile(r".*{% ?load ([\w ]*)$"), self.get_load_completions),
            (re.compile(r".*{% ?block ([\w]*)$"), self.get_block_completions),
            (re.compile(r".*{% ?endblock ([\w]*)$"), self.get_endblock_completions),
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
                # Sort completions because some editors (Helix) will use order
                # as is and wont use sort_text.
                return list(
                    sorted(
                        completion(match, line=line, character=character),
                        key=lambda comp: (
                            comp.sort_text if comp.sort_text else comp.label
                        ),
                    )
                )
        return []

    def get_load_completions(self, match: Match, **kwargs):
        prefix = match.group(1).split(" ")[-1]
        logger.debug(f"Find load matches for: {prefix}")
        return [
            CompletionItem(label=lib, kind=CompletionItemKind.Module)
            for lib in self.workspace_index.libraries.keys()
            if lib != BUILTIN and lib.startswith(prefix)
        ]

    def get_block_completions(self, match: Match, **kwargs):
        prefix = match.group(1).strip()
        logger.debug(f"Find block matches for: {prefix}")
        block_names = []
        re_extends = re.compile(r""".*{% ?extends ['"](.*)['"] ?%}.*""")
        if m := re_extends.search(self.document.source):
            logger.debug(f"Finding available block names for {m.group(1)}")
            block_names = self._recursive_block_names(m.group(1))

        used_block_names = []
        re_block = re.compile(r"{% *block ([\w]*) *%}")
        for line in self.document.lines:
            if matches := re_block.findall(line):
                used_block_names.extend(matches)

        return [
            CompletionItem(label=name, kind=CompletionItemKind.Property)
            for name in block_names
            if name not in used_block_names and name.startswith(prefix)
        ]

    def get_endblock_completions(self, match: Match, line, character):
        prefix = match.group(1).strip()
        logger.debug(f"Find endblock matches for: {prefix}")
        items = {}

        re_block = re.compile(r"{% *block ([\w]*) *%}")
        for text_line in self.document.lines[:line]:
            if matches := re_block.findall(text_line):
                for name in reversed(matches):
                    items.setdefault(
                        name,
                        CompletionItem(
                            label=name,
                            sort_text=f"{999 - len(items)}: {name}",
                            kind=CompletionItemKind.Property,
                        ),
                    )
        return [item for item in items.values() if item.label.startswith(prefix)]

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

    def get_static_completions(self, match: Match, **kwargs):
        prefix = match.group(2)
        logger.debug(f"Find static matches for: {prefix}")
        return [
            CompletionItem(label=static_file, kind=CompletionItemKind.File)
            for static_file in self.workspace_index.static_files
            if static_file.startswith(prefix)
        ]

    def get_url_completions(self, match: Match, **kwargs):
        prefix = match.group(2)
        logger.debug(f"Find url matches for: {prefix}")
        return [
            CompletionItem(
                label=url.name,
                documentation=url.docs,
                kind=CompletionItemKind.Reference,
            )
            for url in self.workspace_index.urls.values()
            if url.name.startswith(prefix)
        ]

    def get_template_completions(self, match: Match, **kwargs):
        prefix = match.group(3)
        logger.debug(f"Find {match.group(1)} matches for: {prefix}")
        return [
            CompletionItem(label=template, kind=CompletionItemKind.File)
            for template in self.workspace_index.templates
            if template.startswith(prefix)
        ]

    def get_tag_completions(self, match: Match, line, character):
        prefix = match.group(1)
        logger.debug(f"Find tag matches for: {prefix}")

        # Get all avaible tags in template
        available_tags = {
            tag.name: tag
            for lib_name in self.loaded_libraries
            for tag in self.workspace_index.libraries.get(lib_name).tags.values()
        }

        # Collect all tags above the current cursor position
        collected_tags = []
        tag_re = re.compile(r"{% ?(\w+).*?%}")
        for text_line in self.document.lines[:line]:
            for tag_name in tag_re.findall(text_line):
                if tag := available_tags.get(tag_name):
                    collected_tags.append(tag)

        # Add all tag completions
        tags = {}
        for tag in available_tags.values():
            tags[tag.name] = CompletionItem(
                label=tag.name,
                documentation=tag.docs,
                sort_text=f"999: {tag.name}",
                kind=CompletionItemKind.Keyword,
            )

        # Add all inner/closing tags
        for index, tag in enumerate(reversed(collected_tags)):
            for tag_name in filter(None, [*tag.inner_tags, tag.closing_tag]):
                tags.setdefault(
                    tag_name,
                    CompletionItem(
                        label=tag_name,
                        sort_text=f"{index}: {tag_name}",
                        kind=CompletionItemKind.Keyword,
                    ),
                )

        return [tag for tag in tags.values() if tag.label.startswith(prefix)]

    def get_filter_completions(self, match: Match, **kwargs):
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
                            kind=CompletionItemKind.Function,
                        )
                        for filt in lib.filters.values()
                    ]
                )
        return [
            filter_name
            for filter_name in filters
            if filter_name.label.startswith(prefix)
        ]

    def get_type_comment_complations(self, match: Match, **kwargs):
        prefix = match.group(1)
        logger.debug(f"Find type comment matches for: {prefix}")

        if "." in prefix:
            from_part = ".".join(prefix.split(".")[:-1])
            import_part = prefix.split(".")[-1]
            code = f"from {from_part} import {import_part}"
        else:
            code = f"import {prefix}"

        return [
            CompletionItem(
                label=comp.name, kind=self._jedi_type_to_completion_kind(comp.type)
            )
            for comp in self.create_jedi_script(code, **kwargs).complete()
        ]

    def get_context_completions(self, match: Match, **kwargs):
        prefix = match.group(2)
        logger.debug(f"Find context matches for: {prefix}")

        if RE_TAGS_NO_CONTEXT.match(match.group(1)):
            return []

        def get_sort_text(comp):
            type_sort = {"statement": "1", "property": "2"}.get(comp.type, "9")
            return f"{type_sort}-{comp.name}".lower()

        if "." in prefix:
            # Find . completions with Jedi
            completions = []
            for comp in self.create_jedi_script(prefix, **kwargs).complete():
                if comp.name.startswith("_"):
                    continue

                _MOST_RECENT_COMPLETIONS[comp.name] = comp
                completions.append(
                    CompletionItem(
                        label=comp.name,
                        sort_text=get_sort_text(comp),
                        kind=self._jedi_type_to_completion_kind(comp.type),
                    )
                )
            return completions
        else:
            # Only context completions
            return [
                CompletionItem(
                    label=var_name,
                    sort_text=var_name.lower(),
                    kind=CompletionItemKind.Variable,
                    detail=f"{var_name}: {var.type}",
                    documentation=var.docs,
                )
                for var_name, var in self.get_context(**kwargs).items()
                if var_name.startswith(prefix)
            ]

    @staticmethod
    def resolve_completion(item: CompletionItem):
        if not item.documentation and item.label in _MOST_RECENT_COMPLETIONS:
            completion = _MOST_RECENT_COMPLETIONS[item.label]
            item.detail = f"({completion.type}) {completion.name}"
            item.documentation = completion.docstring()

        return item

    @staticmethod
    def clear_completions_cache():
        _MOST_RECENT_COMPLETIONS.clear()

    ###################################################################################
    # Hover
    ###################################################################################
    def hover(self, line, character):
        line_fragment = self.document.lines[line][:character]
        matchers = [
            (re.compile(r""".*{% ?url ('|")([\w\-:]*)$"""), self.get_url_hover),
            (re.compile(r"^.*({%|{{) ?[\w \.\|]*\|(\w*)$"), self.get_filter_hover),
            (re.compile(r"^.*{% ?(\w*)$"), self.get_tag_hover),
            (
                re.compile(r".*({{|{% \w+ ).*?([\w\d_\.]*)$"),
                self.get_context_hover,
            ),
        ]
        for regex, hover in matchers:
            if match := regex.match(line_fragment):
                return hover(line, character, match)
        return None

    def get_url_hover(self, line, character, match: Match):
        full_match = self._get_full_hover_name(
            line, character, match.group(2), regex=r"^([\w\d:\-]+).*"
        )
        logger.debug(f"Find url hover for: {full_match}")
        if url := self.workspace_index.urls.get(full_match):
            return Hover(
                contents=url.docs,
            )

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

    def get_context_hover(self, line, character, match: Match):
        context_name = self._get_full_hover_name(line, character, match.group(2))
        logger.debug(f"Find context hover for: {context_name}")

        # first try to resolve variable type locally
        context = self.get_context(line=line, character=character)
        if context_name in context and context[context_name].type:
            return Hover(
                contents=(
                    f"(variable) {context_name}: {context[context_name].type}"
                    f"\n\n{context[context_name].docs}"
                ).strip(),
            )

        # but if not possible, use jedi
        if hlp := self.create_jedi_script(
            context_name, line=line, character=character, execute_last_function=False
        ).help():
            return Hover(
                contents=(
                    f"({hlp[0].type}) {hlp[0].name}: {hlp[0].get_type_hint()}"
                    f"\n\n{hlp[0].docstring()}"
                ).strip(),
            )

        return None

    def _get_full_hover_name(self, line, character, first_part, regex=r"^([\w\d]+).*"):
        if match_after := re.match(regex, self.document.lines[line][character:]):
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
            (re.compile(r""".*{% ?url ('|")([\w\-:]*)$"""), self.get_url_definition),
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
        if match_after := re.match(
            r"""^(.*)('|").*""", self.document.lines[line][character:]
        ):
            template_name = match.group(3) + match_after.group(1)
            logger.debug(f"Find template goto definition for: {template_name}")
            if template := self.workspace_index.templates.get(template_name):
                location, path = template.path.split(":")
                return self.create_location(location, path, 0)

    def get_url_definition(self, line, character, match: Match):
        full_match = self._get_full_definition_name(
            line, character, match.group(2), regex=r"^([\w\d:\-]+).*"
        )
        logger.debug(f"Find url goto definition for: {full_match}")
        if url := self.workspace_index.urls.get(full_match):
            if url.source:
                return self.create_location(*url.source.split(":"))

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
        if gotos := self.create_jedi_script(
            full_match, line=line, character=character
        ).goto(column=len(first_match)):
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

    def _get_full_definition_name(
        self, line, character, first_part, regex=r"^([\w\d]+).*"
    ):
        if match_after := re.match(regex, self.document.lines[line][character:]):
            return first_part + match_after.group(1)
        return first_part
