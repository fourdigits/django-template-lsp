import logging
import re
from functools import cached_property
from re import Match

from pygls.workspace import TextDocument

from djlsp.constants import BUILTIN

logger = logging.getLogger(__name__)


class TemplateParser:
    re_loaded = re.compile(r".*{% ?load ([\w ]*) ?%}$")
    re_load = re.compile(r".*{% ?load ([\w ]*)$")
    re_url = re.compile(r""".*{% ?url ('|")([\w\-:]*)$""")
    re_static = re.compile(r".*{% ?static ('|\")([\w\-\.\/]*)$")
    re_tag = re.compile(r"^.*{% ?(\w*)$")
    re_filter = re.compile(r"^.*({%|{{) ?[\w \.\|]*\|(\w*)$")
    re_template = re.compile(r""".*{% ?(extends|include) ('|")([\w\-:]*)$""")

    def __init__(self, django_data: dict, document: TextDocument):
        self.django_data = django_data
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
                        if lib in self.django_data["libraries"]
                    ]
                )
        logger.debug(f"Loaded libraries: {loaded}")
        return loaded

    def completions(self, line, character):
        line_fragment = self.document.lines[line][:character]

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

        return []

    def get_load_completions(self, match: Match):
        prefix = match.group(1)
        logger.debug(f"Find load matches for: {prefix}")
        return sorted(
            [
                lib
                for lib in self.django_data["libraries"].keys()
                if lib != BUILTIN and lib.startswith(prefix)
            ]
        )

    def get_static_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find static matches for: {prefix}")
        return sorted(
            [
                static_file
                for static_file in self.django_data["static_files"]
                if static_file.startswith(prefix)
            ]
        )

    def get_url_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find url matches for: {prefix}")
        return sorted(
            [url for url in self.django_data["urls"] if url.startswith(prefix)]
        )

    def get_template_completions(self, match: Match):
        prefix = match.group(3)
        logger.debug(f"Find {match.group(1)} matches for: {prefix}")
        logger.debug(self.django_data["templates"])
        return sorted(
            [
                template
                for template in self.django_data["templates"]
                if template.startswith(prefix)
            ]
        )

    def get_tag_completions(self, match: Match):
        prefix = match.group(1)
        logger.debug(f"Find tag matches for: {prefix}")

        tags = []
        for name, lib in self.django_data["libraries"].items():
            if name in self.loaded_libraries:
                tags.extend(lib["tags"])

        return sorted([tag for tag in tags if tag.startswith(prefix)])

    def get_filter_completions(self, match: Match):
        prefix = match.group(2)
        logger.debug(f"Find filter matches for: {prefix}")
        filters = []
        for name, lib in self.django_data["libraries"].items():
            if name in self.loaded_libraries:
                filters.extend(lib["filters"])
        return sorted(
            [filter_name for filter_name in filters if filter_name.startswith(prefix)]
        )
