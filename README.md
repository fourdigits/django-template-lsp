<p align="center">
  <img src="https://github.com/user-attachments/assets/b362a5d6-c124-4751-b7d8-ce715c14ab97" width="128" height="128"/>
</p>
<h1 align="center">Django Template LSP server</h1>

The Django Template LSP server enhances your Django development
experience with powerful features for navigating and editing template files.
This LSP supports:

### Completions

- **Custom Tags and Filters**: Autocomplete for your custom template tags and filters.
- **Template**: Suggestions for `extends` and `includes` statements.
- **Load Tag**: Autocomplete for `{% load %}` tags.
- **Static Files**: Path suggestions for `{% static %}` tags.
- **URLs**: Autocomplete for `{% url %}` tags.

### Go to Definitions

- **Template**: Jump directly to the templates used in `extends` and `includes`.
- **URL Tag**: Navigate to the views referenced in `{% url %}` tags.
- **Tags and Filters**: Quickly access the definitions of custom tags and filters.
- **Context Variables**: Partial support for jumping to context definitions.

### Hover Documentation

- **URLs**: Inline documentation for `{% url %}` tags.
- **Tags and Filters**: Detailed descriptions for template tags and filters.


## Support (tested)

- Python: 3.10, 3.11, 3.12, 3.13, 3.14
- Django: 4.2, 5.0, 5.1, 5.2, 6.0


## Installation

To install the package globally and isolate it from other Python environments, use `pipx`:

```bash
pipx install django-template-lsp
```

Once installed, the Django template LSP server is accessible via the following commands:

- `djlsp`
- `django-template-lsp`

## Options

- `env_directories` (list[string]) default (list of relative or absolute paths): ["env", ".env", "venv", ".venv"]
- `docker_compose_file` (string) default: "docker-compose.yml"
- `docker_compose_service` (string) default: "django"
- `django_settings_module` (string) default (auto detected when empty): ""
- `cache` (boolean/string) default (either true/false or a filepath to the cachefile): false

## Data Collection Method

The Django Template LSP Server collects project data by executing a script in the following order:

1. **Virtual Environment**:
    - Checks for a virtual environment in the root directory within one of these folders: `env`, `.env`, `venv`, or `.venv`.
    - If found, runs the `django-collector.py` script using the virtual environment's Python interpreter.

2. **Docker Compose**:
    - If a Docker Compose file (`docker-compose.yml` by default) is present and includes the specified service (`django` by default), the script is executed within that Docker service.

3. **Global Python**:
    - If neither a virtual environment nor Docker Compose is detected, the script runs using the global `python3` installation on the system.

**Note**: The data collection process will fail if there are Python syntax errors or missing imports in your project.

## Type hints

Due to the highly dynamic nature of Python and Django, it can be challenging to
identify the available context data within templates.  To address this, basic
type hint support is provided directly in the template files:

```html
{# type blog: blogs.models.Blog #}
```

## Plugin system

Django Template LSP supports a plugin system via Python
[entry points](https://packaging.python.org/en/latest/specifications/entry-points/).
Plugins are distributed as separate packages and are automatically discovered at
runtime. Three plugin types are available.

### Collector plugins

Collector plugins run inside the Django subprocess (alongside `django-collector.py`)
and can extend or modify the data collected from a Django project — for example,
to add template context variables from a custom framework.

```python
# mypackage/plugin.py
from djlsp.plugins import CollectorPlugin

class MyCollectorPlugin(CollectorPlugin):
    def collect(self, collector) -> None:
        # `collector` exposes these mutable attributes:
        #   templates: dict[str, dict]
        #   urls: dict[str, dict]
        #   libraries: dict[str, dict]
        #   static_files: list[str]
        #   global_template_context: dict[str, str | None]
        #   file_watcher_globs: list[str]
        #   plugin_data: dict  ← custom data for parser/context plugins
        collector.global_template_context["my_global"] = "mypackage.MyClass"

        # Store custom data to be read by a parser or context plugin
        collector.plugin_data["my_custom_data"] = ["foo", "bar"]
```

Custom data stored in `collector.plugin_data` is passed through the collector
JSON and becomes available in parser and context plugins as
`self.workspace_index.plugin_data`:

```python
class MyParserPlugin(ParserPlugin):
    def completions(self, line: int, character: int) -> list:
        items = self.workspace_index.plugin_data.get("my_custom_data", [])
        ...
```

Register it in your `pyproject.toml`:

```toml
[project.entry-points."djlsp.collector_plugins"]
myplugin = "mypackage.plugin:MyCollectorPlugin"
```

### Parser plugins

Parser plugins run in the LSP server process and can provide completions, hover
documentation, and goto-definition for cases not handled by the built-in matchers.
They are called as a fallback when no built-in matcher fires.

```python
from djlsp.plugins import ParserPlugin

class MyParserPlugin(ParserPlugin):
    def completions(self, line: int, character: int) -> list:
        return []  # return lsprotocol CompletionItem instances

    def hover(self, line: int, character: int):
        return None  # return an lsprotocol Hover instance or None

    def goto_definition(self, line: int, character: int):
        return None  # return an lsprotocol Location instance or None
```

Register it in your `pyproject.toml`:

```toml
[project.entry-points."djlsp.parser_plugins"]
myplugin = "mypackage.plugin:MyParserPlugin"
```

### Context plugins

Context plugins run in the LSP server process and can supply additional template
context variables to supplement those collected during data collection.

```python
from djlsp.plugins import ContextPlugin
from djlsp.index import Variable

class MyContextPlugin(ContextPlugin):
    def get_context(self, *, line: int, character: int, context: dict) -> dict:
        return {"my_var": Variable(type="mypackage.MyModel")}
```

Register it in your `pyproject.toml`:

```toml
[project.entry-points."djlsp.context_plugins"]
myplugin = "mypackage.plugin:MyContextPlugin"
```

### Built-in plugins

| Entry point group | Plugin name | Description |
|---|---|---|
| `djlsp.collector_plugins` | `wagtail` | Adds Wagtail `Page` model context variables to their bound templates. Activates automatically when `wagtail` is importable. |

## Editors

### Helix

In your global or project `languages.toml` add the following

```toml
[[language]]
name = "htmldjango"
file-types = ["html"]
```

Project settings `.helix/languages.toml`:

```toml
[language-server.djlsp.config]
django_settings_module="<your.settings.module>"
```

### Neovim

In your lspconfig add the following

```lua
require'lspconfig'.djlsp.setup{
    cmd = { "<path-to-djlsp>" },
    init_options = {
        django_settings_module = "<your.settings.module>",
        docker_compose_file = "docker-compose.yml",
        docker_compose_service = "django"
    }
}
```

### VSCode

To use the Django template LSP with VSCode read the following [readme](vscode/README.md)

## Development

Install development dependencies:

```bash
make develop
```

For local development, using [Helix](https://helix-editor.com) is the easiest approach.
The configuration for using the source Django template language server, with logging enabled, is already set up.

To start the Helix editor with the environment activated and the correct workspace loaded, run:

```bash
make helix
```

### neovim

Locally install the package

``` sh
make develop
```

Point neovim's `djlsp` to the locally installed copy

``` lua
require("lspconfig").djlsp.setup({
        cmd = { "/path/to/django-template-lsp/.venv/bin/djlsp" },
        root_dir = require("lspconfig.util").root_pattern("manage.py", ".git"),
})
```

If you want to access the log while developing, add the `--enable-log` flag to the cmd.
The logfile will be written to a file in your current working directory named `djlsp.log`.

``` lua
require("lspconfig").djlsp.setup({
        cmd = { "/path/to/django-template-lsp/.venv/bin/djlsp", "--enable-log" },
})
```
