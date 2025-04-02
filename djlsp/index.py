from dataclasses import dataclass, field


@dataclass
class Variable:
    type: str | None = None
    docs: str = ""
    value: str = ""


@dataclass
class Template:
    name: str = ""
    path: str = ""
    extends: str | None = None
    blocks: list[str] | None = None
    context: dict[str, Variable] = field(default_factory=dict)


@dataclass
class Url:
    name: str = ""
    docs: str = ""
    source: str = ""


@dataclass
class Tag:
    name: str = ""
    docs: str = ""
    source: str = ""
    inner_tags: list[str] = field(default_factory=list)
    closing_tag: str = ""


@dataclass
class Filter:
    name: str = ""
    docs: str = ""
    source: str = ""


@dataclass
class Library:
    name: str = ""
    tags: dict[str, Tag] = field(default_factory=dict)
    filters: dict[str, Filter] = field(default_factory=dict)


@dataclass
class WorkspaceIndex:
    src_path: str = ""
    env_path: str = ""
    file_watcher_globs: list[str] = field(default_factory=list)
    static_files: list[str] = field(default_factory=list)
    urls: dict[str, Url] = field(default_factory=dict)
    libraries: dict[str, Library] = field(default_factory=dict)
    templates: dict[str, Template] = field(default_factory=dict)
    global_template_context: dict[str, Variable] = field(default_factory=dict)

    def update(self, django_data: dict):
        self.file_watcher_globs = django_data.get(
            "file_watcher_globs", self.file_watcher_globs
        )
        self.static_files = django_data.get("static_files", self.static_files)
        self.urls = {
            name: Url(
                name=name,
                docs=options.get("docs", ""),
                source=options.get("source", ""),
            )
            for name, options in django_data.get("urls", {}).items()
        }

        self.libraries = {
            lib_name: Library(
                name=lib_name,
                filters={
                    name: Filter(
                        name=name,
                        docs=filter_options.get("docs", ""),
                        source=filter_options.get("source", ""),
                    )
                    for name, filter_options in lib_data.get("filters", {}).items()
                },
                tags={
                    tag: Tag(
                        name=tag,
                        docs=tag_options.get("docs"),
                        source=tag_options.get("source", ""),
                        inner_tags=tag_options.get("inner_tags", []),
                        closing_tag=tag_options.get("closing_tag"),
                    )
                    for tag, tag_options in lib_data.get("tags", {}).items()
                },
            )
            for lib_name, lib_data in django_data.get("libraries", {}).items()
        }

        self.templates = {
            name: Template(
                name=name,
                **{
                    **options,
                    "context": {
                        var_name: (
                            Variable(**type_)
                            if isinstance(type_, dict)
                            else Variable(type=type_)
                        )
                        for var_name, type_ in options.get("context", {}).items()
                    },
                },
            )
            for name, options in django_data.get("templates", {}).items()
        }

        self.global_template_context = {
            name: (
                Variable(**type_) if isinstance(type_, dict) else Variable(type=type_)
            )
            for name, type_ in django_data.get("global_template_context", {}).items()
        }
