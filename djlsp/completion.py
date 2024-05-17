import re

TAGS = [
    "autoescape",
    "block",
    "comment",
    "filter",
    "for",
    "if",
    "ifchanged",
    "spaceless",
    "verbatim",
    "with",
    # TODO: check if i18n is loaded
    "blocktranslate",
    # TODO: check if l10n is loaded
    "localize",
    # TODO: check if tz is loaded
    "localtime",
    "timezone",
]

SIMPLE_TAGS = [
    "csrf_token",
    "cycle",
    "debug",
    "extends",
    "firstof",
    "include",
    "load",
    "lorem",
    "now",
    "regroup",
    "resetcycle",
    "templatetag",
    "url",
    "widthratio",
    # TODO: check if statis is loaded
    "static",
    # TODO: check if i18n is loaded
    "translate",
    # TODO: Hack to make empy and else work, should check if inside if or for
    "empty",
    "else",
]

FILTERS = [
    "add",
    "addslashes",
    "capfirst",
    "center",
    "cut",
    "date",
    "default",
    "default_if_none",
    "dictsort",
    "dictsortreversed",
    "divisibleby",
    "escape",
    "escapejs",
    "escapeseq",
    "filesizeformat",
    "first",
    "floatformat",
    "force_escape",
    "get_digit",
    "iriencode",
    "join",
    "json_script",
    "last",
    "length",
    "length_is",
    "linebreaks",
    "linebreaksbr",
    "linenumbers",
    "ljust",
    "lower",
    "make_list",
    "phone2numeric",
    "pluralize",
    "pprint",
    "random",
    "rjust",
    "safe",
    "safeseq",
    "slice",
    "slugify",
    "stringformat",
    "striptags",
    "time",
    "timesince",
    "timeuntil",
    "title",
    "truncatechars",
    "truncatechars_html",
    "truncatewords",
    "truncatewords_html",
    "unordered_list",
    "upper",
    "urlencode",
    "urlize",
    "urlizetrunc",
    "wordcount",
    "wordwrap",
    "yesno",
    # TODO: check if l10n is loaded
    "localize",
    "unlocalize",
    # TODO: check if tz is loaded
    "localtime",
    "utc",
    "timezone",
]

re_tag = re.compile(r"^.*{% ?(\w*)$")
re_end_tag = re.compile(r"^.*{% ?(e\w*)$")
re_filter = re.compile(r"^.*({%|{{) ?[\w \.\|]*\|(\w*)$")


def get_completions(line_fragment):
    # TODO: Maybe replace logic with tree-sitter

    if match := re_filter.match(line_fragment):
        search = match.group(2).lower()
        for filter_name in FILTERS:
            if filter_name.startswith(search):
                yield filter_name
    elif match := re_end_tag.match(line_fragment):
        # TODO only show end tags for open/used tags
        search = match.group(1).lower()
        for tag in TAGS:
            end_tag = f"end{tag}"
            if end_tag.startswith(search):
                yield end_tag
    elif match := re_tag.match(line_fragment):
        search = match.group(1)
        for tag in TAGS + SIMPLE_TAGS:
            if tag.startswith(search):
                yield tag
