from dataclasses import dataclass, field


@dataclass
class Template:
    name: str = ""
    extends: str | None = None
    loaded_libraries: list[str] | None = None
    blocks: list[str] | None = None
    context: dict = field(default_factory=dict)


@dataclass
class Tag:
    name: str = ""
    in_between_tags: list[str] = ""
    closing_tag: str = ""


@dataclass
class Library:
    name: str = ""
    tags: dict[str, Tag] = field(default_factory=dict)
    filters: list[str] = field(default_factory=list)


@dataclass
class WorkspaceIndex:
    file_watcher_globs: [str] = field(default_factory=list)
    static_files: [str] = field(default_factory=list)
    urls: [str] = field(default_factory=list)
    libraries: dict[str, Library] = field(default_factory=dict)
    templates: dict[str, Template] = field(default_factory=dict)

    def update(self, django_data: dict):
        self.file_watcher_globs = django_data.get(
            "file_watcher_globs", self.file_watcher_globs
        )
        self.static_files = django_data.get("static_files", self.static_files)
        self.urls = django_data.get("urls", self.urls)

        # TODO: add support in django collector
        # if libraries := django_data.get("libraries"):
        #     self.libraries = {
        #         library.get("name"): Library(
        #             name=library.get("name"),
        #             filters=library.get("filters", []),
        #             tags={
        #                 tag.get("name"): Tag(
        #                     name=tag.get("name"),
        #                     in_between_tags=tag.get("in_between_tags", []),
        #                     closing_tag=tag.get("closing_tag"),
        #                 )
        #                 for tag in library.get("tags", [])
        #             },
        #         )
        #         for library in libraries
        #     }

        self.templates = {
            name: Template(name=name, **options)
            for name, options in django_data.get("templates", {}).items()
        }
