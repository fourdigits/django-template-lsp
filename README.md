# Django template LSP

A simple Django template LSP for completions that has support for:

- Custom `tags` and `filters`
- templates for `extends` and `includes`
- load tag
- static files
- urls

## Support (tested)

- Python: 3.10, 3.11, 3.12
- Django: 3.2, 4.2, 5.0


## Install

    pip install django-template-lsp

## Options

- `docker_compose_file` (string) default: "docker-compose.yml"
- `docker_compose_service` (string) default: "django"
- `django_settings_module` (string) default: ""

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

