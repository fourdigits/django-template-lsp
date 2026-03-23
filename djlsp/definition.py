import logging
import re
from re import Match

from lsprotocol.types import Location, Position, Range

logger = logging.getLogger(__name__)


class DefinitionMixin:
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
            logger.debug("Find template goto definition for: %s", template_name)
            if template := self.workspace_index.templates.get(template_name):
                location, path = template.path.split(":")
                return self.create_location(location, path, 0)
        return None

    def get_url_definition(self, line, character, match: Match):
        full_match = self._get_full_definition_name(
            line, character, match.group(2), regex=r"^([\w\d:\-]+).*"
        )
        logger.debug("Find url goto definition for: %s", full_match)
        if url := self.workspace_index.urls.get(full_match):
            if url.source:
                return self.create_location(*url.source.split(":"))
        return None

    def get_tag_definition(self, line, character, match: Match):
        full_match = self._get_full_definition_name(line, character, match.group(1))
        logger.debug("Find tag goto definition for: %s", full_match)
        for lib in self.loaded_libraries:
            if tag := self.workspace_index.libraries[lib].tags.get(full_match):
                if tag.source:
                    return self.create_location(*tag.source.split(":"))
        return None

    def get_filter_definition(self, line, character, match: Match):
        full_match = self._get_full_definition_name(line, character, match.group(2))
        logger.debug("Find filter goto definition for: %s", full_match)
        for lib in self.loaded_libraries:
            if filter_ := self.workspace_index.libraries[lib].filters.get(full_match):
                if filter_.source:
                    return self.create_location(*filter_.source.split(":"))
        return None

    def get_context_definition(self, line, character, match: Match):
        first_match = match.group(2)
        full_match = self._get_full_definition_name(line, character, first_match)
        logger.debug("Find context goto definition for: %s", full_match)
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
        return None

    def _get_full_definition_name(
        self, line, character, first_part, regex=r"^([\w\d]+).*"
    ):
        if match_after := re.match(regex, self.document.lines[line][character:]):
            return first_part + match_after.group(1)
        return first_part
