# Django Template LSP vscode extension

This extension provides Django Template Language completions for Visual Studio Code.

## Usage

Make sure you have installed the python `django-template-lsp` package on your system. You can install it using pipx:

```bash
pipx install django-template-lsp
```

Then, install the `djlsp` extension from the Visual Studio Code marketplace.


## Settings

Within the `settings.json` file, you can configure the following settings:
- `djangoTemplateLsp.dockerComposeFile`: Docker Compose file name. Default: `docker-compose.yml`
- `djangoTemplateLsp.dockerServiceName`: Docker service name. Default: `django`
- `djangoTemplateLsp.djangoSettingsModule`: Django settings module. Default: ``
- `djangoTemplateLsp.enableLogging`: Enable logging. Default: `false`

