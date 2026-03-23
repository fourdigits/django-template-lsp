import hashlib
import logging
import re
import time
from functools import cached_property
from textwrap import dedent

import jedi
from pygls.workspace import TextDocument

from djlsp.constants import BUILTIN
from djlsp.index import Variable, WorkspaceIndex

logger = logging.getLogger(__name__)


class ContextInferenceMixin:
    workspace_index: WorkspaceIndex
    jedi_project: jedi.Project
    document: TextDocument

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
        logger.debug("Loaded libraries: %s", loaded)
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

        stack = self._collect_scope_stack(line=line)
        if stack:
            logger.debug("Stack not empty for line=%s len(stack)=%s", line, len(stack))

        for tag_name, match in stack:
            logger.debug("  %s %r %r", tag_name, match, match.groups())
            if tag_name == "for":
                self._apply_for_scope_context(context, match)
            elif tag_name == "with":
                self._apply_with_scope_context(context, match)

        # As tag
        # TODO: integrate into scope matcher
        re_as = re.compile(r".*{%.*as ([\w ]+) %}.*$")
        for src_line in self.document.lines:
            if match := re_as.match(src_line):
                for variable in match.group(1).split(" "):
                    if variable_stripped := variable.strip():
                        context[variable_stripped] = Variable()

        return context

    def _collect_scope_stack(self, *, line: int):
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
        stack: list[tuple[str, re.Match[str]]] = []
        for line_idx, src_line in enumerate(self.document.lines):
            # only analyze until the current line
            if line and line_idx > line:
                break

            for tag_name, re_start, re_end in scoped_tags:
                if match := re_start.match(src_line):
                    stack.append((tag_name, match))
                    break
                if re_end.match(src_line):
                    self._close_scope_tag(stack, tag_name)
                    break
        return stack

    def _close_scope_tag(self, stack: list[tuple[str, re.Match[str]]], tag_name: str):
        if not stack:
            logger.debug("Closing tag has no matching opening tag: %s", tag_name)
            return

        if stack[-1][0] == tag_name:
            stack.pop()
            return

        # Tolerate malformed templates by recovering from mismatched end tags.
        for idx in range(len(stack) - 1, -1, -1):
            if stack[idx][0] == tag_name:
                logger.debug(
                    "Recovering mismatched closing tag %s by dropping %s open scope(s)",
                    tag_name,
                    len(stack) - idx,
                )
                del stack[idx:]
                return

        logger.debug("Closing tag does not match any opening tag: %s", tag_name)

    def _apply_for_scope_context(self, context: dict, match: re.Match[str]):
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
            context[loop_variables.strip()] = Variable(value=f"next(iter({variable}))")

    def _apply_with_scope_context(self, context: dict, match: re.Match[str]):
        for assignment in match.group(1).split(" "):
            split_assignment = assignment.split("=")
            if len(split_assignment) == 2:
                context[split_assignment[0].strip()] = Variable(
                    value=self._django_variable_to_python(
                        split_assignment[1].strip(), context
                    )
                )

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
                    "Failed to transform variable '%s' (got until %s)", variable, res
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
            "Variable '%s' transformed to '%s' in %.4fs", variable, res, total_time
        )

        return res
