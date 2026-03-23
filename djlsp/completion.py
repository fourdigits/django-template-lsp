import logging
import re
from re import Match

from jedi.api.classes import Completion
from lsprotocol.types import CompletionItem, CompletionItemKind

from djlsp.constants import BUILTIN

logger = logging.getLogger(__name__)

RE_TAGS_NO_CONTEXT = re.compile(r"{% ?(end.*|comment|csrf_token|debug|spaceless)")

_MOST_RECENT_COMPLETIONS: dict[str, Completion] = {}


def clear_completions_cache():
    _MOST_RECENT_COMPLETIONS.clear()


class CompletionMixin:
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
        logger.debug("Find load matches for: %s", prefix)
        return [
            CompletionItem(label=lib, kind=CompletionItemKind.Module)
            for lib in self.workspace_index.libraries.keys()
            if lib != BUILTIN and lib.startswith(prefix)
        ]

    def get_block_completions(self, match: Match, **kwargs):
        prefix = match.group(1).strip()
        logger.debug("Find block matches for: %s", prefix)
        block_names = []
        re_extends = re.compile(r""".*{% ?extends ['"](.*)['"] ?%}.*""")
        if m := re_extends.search(self.document.source):
            logger.debug("Finding available block names for %s", m.group(1))
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
        logger.debug("Find endblock matches for: %s", prefix)
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
        logger.debug("Find static matches for: %s", prefix)
        return [
            CompletionItem(label=static_file, kind=CompletionItemKind.File)
            for static_file in self.workspace_index.static_files
            if static_file.startswith(prefix)
        ]

    def get_url_completions(self, match: Match, **kwargs):
        prefix = match.group(2)
        logger.debug("Find url matches for: %s", prefix)
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
        logger.debug("Find %s matches for: %s", match.group(1), prefix)
        return [
            CompletionItem(label=template, kind=CompletionItemKind.File)
            for template in self.workspace_index.templates
            if template.startswith(prefix)
        ]

    def get_tag_completions(self, match: Match, line, character):
        prefix = match.group(1)
        logger.debug("Find tag matches for: %s", prefix)

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
        logger.debug("Find filter matches for: %s", prefix)
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
        logger.debug("Find type comment matches for: %s", prefix)

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
        logger.debug("Find context matches for: %s", prefix)

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
