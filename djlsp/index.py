from dataclasses import dataclass, field


@dataclass
class Template:
    file_path: str = ""
    workspace_file_path: str = ""
    context: dict = field(default_factory=dict)
    # Attributes filled by parser
    extends: str | None = None
    loaded_libraries: list[str] | None = None
    blocks: list[str] | None = None

    def clear(self):
        self.extends = None
        self.blocks = None


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

        # TODO: Add Support in django collector
        # Update templates
        # if templates := django_data.get("templates"):
        #     found_templates = []
        #     for template in templates:
        #         # TODO: how to handle template override
        #         file_path = template.get("file_path")
        #         found_templates.append(file_path)
        #         if file_path in self.templates:
        #             self.templates[file_path].context = template.get("context", dict)
        #         else:
        #             self.templates[file_path] = Template(
        #                 file_path=file_path,
        #                 workspace_file_path=template.get("workspace_file_path", ""),
        #                 context=template.get("context", dict),
        #             )

        #     self.templates = [t for t in self.templates if t in found_templates]
