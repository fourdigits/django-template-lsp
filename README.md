# Django Template Language Server (LSP)

The Django Template Language Server (LSP) enhances your Django development
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

- Python: 3.10, 3.11, 3.12
- Django: 3.2, 4.2, 5.0


## Install

    pip install django-template-lsp

## Options

- `docker_compose_file` (string) default: "docker-compose.yml"
- `docker_compose_service` (string) default: "django"
- `django_settings_module` (string) default (auto detected when empty): ""

## Type hints

Due to the highly dynamic nature of Python and Django, it can be challenging to
identify the available context data within templates.  To address this, basic
type hint support is provided directly in the template files:

```html
{# type blog: blogs.models.Blog #}
```

## Editors

### Helix

In your global or project `languages.toml` add the following

```toml
[language-server.djlsp]
command = "djlsp"

[[language]]
name = "html"
language-servers = [ "vscode-html-language-server", "djlsp" ]
```

Project settings `.helix/languages.toml`:

```toml
[language-server.djlsp.config]
django_settings_modules="<your.settings.module>"
```

### Neovim

In your lspconfig add the following

```lua
require'lspconfig'.djlsp.setup{
    cmd = { "<path-to-djlsp>" },
    init_options = {
        djlsp = {
            django_settings_module = "<your.settings.module>"
            docker_compose_file = "docker-compose.yml",
            docker_compose_service = "django"
        }
    }
}
```

### VSCode

To use the Django template LSP with VSCode read the following [readme](vscode/README.md)

