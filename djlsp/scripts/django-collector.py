import argparse
import importlib
import inspect
import json
import os
import sys

import django
from django.apps import apps
from django.conf import settings
from django.contrib.staticfiles.finders import get_finders
from django.template.backends.django import get_installed_libraries
from django.template.engine import Engine
from django.template.library import InvalidTemplateLibrary
from django.template.utils import get_app_template_dirs
from django.urls import URLPattern, URLResolver

# Some tags are added with a Node, like end*, elif else.
# TODO: Find a way of collecting these, for now hardcoded list
LIBRARIES_NODE_TAGS = {
    "__builtins__": [
        # autoescape
        "endautoescape",
        # filter
        "endfilter",
        # for
        "empty",
        "endfor",
        # if
        "else",
        "elif",
        "endif"
        # ifchanged
        "endifchanged",
        # spaceless
        "endspaceless",
        # verbatim
        "endverbatim",
        # with
        "endwith",
        # block
        "endblock",
    ],
    "cache": [
        # cache    sys.path.insert(0, dance_path)
        "endcache",
    ],
    "i18n": [
        # language
        "endlanguage",
    ],
    "l10n": [
        # localize
        "endlocalize",
    ],
    "tz": [
        # localtime
        "endlocaltime",
        # timezone
        "endtimezone",
    ],
}


def get_file_watcher_globs():
    """
    File watcher glob patterns used to trigger this collector script

    https://microsoft.github.io/language-server-protocol/specifications/lsp/3.17/specification/#pattern
    """
    patterns = [
        "**/templates/**",
        "**/templatetags/**",
        "**/static/**",
    ]

    for static_path in settings.STATICFILES_DIRS:
        static_folder = os.path.basename(static_path)
        if static_folder != "static":
            patterns.append(f"**/{static_folder}/**")

    for template_path in [
        *Engine.get_default().dirs,
        *get_app_template_dirs("templates"),
    ]:
        template_folder = os.path.basename(template_path)
        if template_folder != "templates":
            patterns.append(f"**/{template_folder}/**")

    return patterns


def get_static_files():
    # TODO: Add option to ignore some static folders
    # (like static that is generated with a JS bundler)
    static_paths = []
    for finder in get_finders():
        for path, _ in finder.list(None):
            static_paths.append(path)
    return static_paths


def get_urls():
    try:
        urlpatterns = __import__(settings.ROOT_URLCONF, {}, {}, [""]).urlpatterns
    except Exception:
        return []

    def recursive_get_views(urlpatterns, namespace=None):
        views = []
        for p in urlpatterns:
            if isinstance(p, URLPattern):
                if not p.name:
                    name = p.name
                elif namespace:
                    name = "{0}:{1}".format(namespace, p.name)
                else:
                    name = p.name
                views.append(name)
            elif isinstance(p, URLResolver):
                try:
                    patterns = p.url_patterns
                except ImportError:
                    continue
                if namespace and p.namespace:
                    _namespace = "{0}:{1}".format(namespace, p.namespace)
                else:
                    _namespace = p.namespace or namespace
                views.extend(recursive_get_views(patterns, namespace=_namespace))
        return list(filter(None, views))

    return recursive_get_views(urlpatterns)


def get_libraries():
    libraries = {
        "__builtins__": {
            "tags": [],
            "filters": [],
        }
    }

    # Collect builtins
    for lib_mod_path in Engine.get_default().builtins:
        lib = importlib.import_module(lib_mod_path).register
        libraries["__builtins__"]["tags"].extend(list(lib.tags.keys()))
        libraries["__builtins__"]["filters"].extend(list(lib.filters.keys()))

    # Get Django templatetags
    django_path = inspect.getabsfile(django.templatetags)
    django_mod_files = os.listdir(os.path.dirname(django_path))
    for django_lib in [
        i[:-3] for i in django_mod_files if i.endswith(".py") and i[0] != "_"
    ]:
        try:
            lib = get_installed_libraries()[django_lib]
            lib = importlib.import_module(lib).register
            libraries[django_lib] = {
                "tags": list(lib.tags.keys()),
                "filters": list(lib.filters.keys()),
            }
        except (InvalidTemplateLibrary, KeyError):
            continue

    for app_config in apps.get_app_configs():
        app = app_config.name
        try:
            templatetag_mod = __import__(app + ".templatetags", {}, {}, [""])
        except ImportError:
            continue

        mod_path = inspect.getabsfile(templatetag_mod)
        mod_files = os.listdir(os.path.dirname(mod_path))
        tag_files = [i[:-3] for i in mod_files if i.endswith(".py") and i[0] != "_"]

        for taglib in tag_files:
            try:
                lib = get_installed_libraries()[taglib]
                lib = importlib.import_module(lib).register
            except (InvalidTemplateLibrary, KeyError):
                continue

            libraries[taglib] = {
                "tags": list(lib.tags.keys()),
                "filters": list(lib.filters.keys()),
            }

    # Add node tags
    for lib_name, tags in LIBRARIES_NODE_TAGS.items():
        if lib_name in libraries:
            libraries[lib_name]["tags"].extend(tags)

    return libraries


def get_templates():
    template_files = []
    for templates_dir in [
        *Engine.get_default().dirs,
        *get_app_template_dirs("templates"),
    ]:
        for root, dirs, files in os.walk(templates_dir):
            for file in files:
                template_files.append(
                    os.path.relpath(os.path.join(root, file), templates_dir)
                )
    return template_files


def collect_project_data():
    return {
        "file_watcher_globs": get_file_watcher_globs(),
        "static_files": get_static_files(),
        "urls": get_urls(),
        "libraries": get_libraries(),
        "templates": get_templates(),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="""
            Collect django project information for LSP.
            pure python script that is runned in project environment for using django.
        """
    )
    parser.add_argument("--django-settings-module", action="store", type=str)
    parser.add_argument("--project-src", action="store", type=str)
    args = parser.parse_args()

    if args.django_settings_module:
        # TODO: Auto detect when empty?
        os.environ.setdefault(
            "DJANGO_SETTINGS_MODULE",
            args.django_settings_module,
        )

    if args.project_src:
        sys.path.insert(0, args.project_src)
    else:
        sys.path.insert(0, os.getcwd())

    django.setup()

    print(json.dumps(collect_project_data(), indent=4))
