# Django template LSP

A simple Django template LSP for completions



## Install

    pip install django-template-lsp


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
