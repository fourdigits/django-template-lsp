import logging
import re
from re import Match

from lsprotocol.types import Hover

logger = logging.getLogger(__name__)


class HoverMixin:
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
        logger.debug("Find url hover for: %s", full_match)
        if url := self.workspace_index.urls.get(full_match):
            return Hover(contents=url.docs)
        return None

    def get_filter_hover(self, line, character, match: Match):
        filter_name = self._get_full_hover_name(line, character, match.group(2))
        logger.debug("Find filter hover for: %s", filter_name)
        for lib in self.workspace_index.libraries.values():
            if lib.name in self.loaded_libraries and filter_name in lib.filters:
                return Hover(contents=lib.filters[filter_name].docs)
        return None

    def get_tag_hover(self, line, character, match: Match):
        tag_name = self._get_full_hover_name(line, character, match.group(1))
        logger.debug("Find tag hover for: %s", tag_name)
        for lib in self.workspace_index.libraries.values():
            if lib.name in self.loaded_libraries and tag_name in lib.tags:
                return Hover(contents=lib.tags[tag_name].docs)
        return None

    def get_context_hover(self, line, character, match: Match):
        context_name = self._get_full_hover_name(line, character, match.group(2))
        logger.debug("Find context hover for: %s", context_name)

        # first try to resolve variable type locally
        context = self.get_context(line=line, character=character)
        if context_name in context and context[context_name].type:
            return Hover(
                contents=(
                    f"(variable) {context_name}: {context[context_name].type}"
                    f"\n\n{context[context_name].docs}"
                ).strip()
            )

        # but if not possible, use jedi
        if hlp := self.create_jedi_script(
            context_name, line=line, character=character, execute_last_function=False
        ).help():
            return Hover(
                contents=(
                    f"({hlp[0].type}) {hlp[0].name}: {hlp[0].get_type_hint()}"
                    f"\n\n{hlp[0].docstring()}"
                ).strip()
            )

        return None

    def _get_full_hover_name(self, line, character, first_part, regex=r"^([\w\d]+).*"):
        if match_after := re.match(regex, self.document.lines[line][character:]):
            return first_part + match_after.group(1)
        return first_part
