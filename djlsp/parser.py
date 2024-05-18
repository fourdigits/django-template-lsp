import re
from re import Match

from pygls.workspace import TextDocument

from djlsp.constants import FILTERS, SIMPLE_TAGS, TAGS


class TemplateParser:
    re_load = re.compile(r".*{% ?load ([\w ]*)$")
    re_url = re.compile(r""".*{% ?url ('|")([\w\-:]*)$""")
    re_static = re.compile(r".*{% ?static ('|\")([\w\-\.]*)$")
    re_tag = re.compile(r"^.*{% ?(\w*)$")
    re_filter = re.compile(r"^.*({%|{{) ?[\w \.\|]*\|(\w*)$")

    def __init__(self, document: TextDocument):
        self.document: TextDocument = document
        self.loaded_libraries = []
        self.context = []
        self.blocks = []

        self.parse()

    def parse(self):
        # TODO: Find loaded libraries
        # TODO: Find avaible context
        # TODO: Find blocks
        pass

    def completions(self, line, character):
        line_fragment = self.document.lines[line][:character]

        if match := self.re_load.match(line_fragment):
            return self.get_load_completions(match)
        if match := self.re_url.match(line_fragment):
            return self.get_url_completions(match)
        elif match := self.re_static.match(line_fragment):
            return self.get_static_completions(match)
        elif match := self.re_tag.match(line_fragment):
            return self.get_tag_completions(match)
        elif match := self.re_filter.match(line_fragment):
            return self.get_filter_completions(match)

        return []

    def get_load_completions(self, match: Match):
        libraries = [  # TODO: Find all avaible libraries
            "static",
            "humanize",
            "tz",
            "l10n",
            "i18n",
        ]

        *loaded, prefix = match.group(1).split(" ")

        return sorted(
            [lib for lib in libraries if lib.startswith(prefix) and lib not in loaded]
        )

    def get_static_completions(self, match: Match):
        # TODO: Find static files
        return []

    def get_url_completions(self, match: Match):
        # TODO: Read django urls
        return []

    def get_tag_completions(self, match: Match):
        # TODO: use tags from loaded_libraries
        prefix = match.group(1)
        completions = []

        for tag in TAGS:
            if tag.startswith(prefix):
                completions.append(tag)
            end_tag = f"end{tag}"
            if end_tag.startswith(end_tag):
                completions.append(end_tag)

        for simple_tag in SIMPLE_TAGS:
            if simple_tag.startswith(prefix):
                completions.append(simple_tag)

        return sorted(completions)

    def get_filter_completions(self, match: Match):
        # TODO: use filters from loaded_libraries
        prefix = match.group(2)
        return sorted(
            [filter_name for filter_name in FILTERS if filter_name.startswith(prefix)]
        )
