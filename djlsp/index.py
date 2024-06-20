from dataclasses import dataclass, field


@dataclass
class Template:
    name: str = ""
    extends: str | None = None
    blocks: list[str] | None = None
    context: dict = field(default_factory=dict)


@dataclass
class Tag:
    name: str = ""
    docs: str = ""
    inner_tags: list[str] = ""
    closing_tag: str = ""


@dataclass
class Filter:
    name: str = ""
    docs: str = ""


@dataclass
class Library:
    name: str = ""
    tags: dict[str, Tag] = field(default_factory=dict)
    filters: dict[str, Filter] = field(default_factory=dict)


@dataclass
class WorkspaceIndex:
    file_watcher_globs: [str] = field(default_factory=list)
    static_files: [str] = field(default_factory=list)
    urls: [str] = field(default_factory=list)
    libraries: dict[str, Library] = field(default_factory=dict)
    templates: dict[str, Template] = field(default_factory=dict)
    global_template_context: dict[str, str] = field(default_factory=dict)
    object_types: dict[str, dict] = field(default_factory=dict)

    def update(self, django_data: dict):
        self.file_watcher_globs = django_data.get(
            "file_watcher_globs", self.file_watcher_globs
        )
        self.static_files = django_data.get("static_files", self.static_files)
        self.urls = django_data.get("urls", self.urls)

        self.libraries = {
            lib_name: Library(
                name=lib_name,
                filters={
                    name: Filter(
                        name=name,
                        docs=filter_options.get("docs", ""),
                    )
                    for name, filter_options in lib_data.get("filters", {}).items()
                },
                tags={
                    tag: Tag(
                        name=tag,
                        docs=tag_options.get("docs"),
                        inner_tags=tag_options.get("inner_tags", []),
                        closing_tag=tag_options.get("closing_tag"),
                    )
                    for tag, tag_options in lib_data.get("tags", {}).items()
                },
            )
            for lib_name, lib_data in django_data.get("libraries", {}).items()
        }

        self.templates = {
            name: Template(name=name, **options)
            for name, options in django_data.get("templates", {}).items()
        }

        self.global_template_context = django_data.get("global_template_context", {})
        self.object_types = django_data.get("object_types", {})
