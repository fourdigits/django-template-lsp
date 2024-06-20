import argparse
import importlib
import inspect
import json
import os
import re
import sys
from unittest.mock import patch

import django
from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles.finders import get_finders
from django.template.backends.django import get_installed_libraries
from django.template.engine import Engine
from django.template.library import InvalidTemplateLibrary
from django.template.utils import get_app_template_dirs
from django.urls import URLPattern, URLResolver

# Some tags are added with a Node, like end*, elif else.
# TODO: Find a way of collecting these, for now hardcoded list
LIBRARIES_NODE_TAGS = {
    "__builtins__": {
        "autoescape": {
            "closing_tag": "endautoescape",
        },
        "filter": {
            "closing_tag": "endfilter",
        },
        "for": {
            "inner_tags": [
                "empty",
            ],
            "closing_tag": "endfor",
        },
        "if": {
            "inner_tags": [
                "else",
                "elif",
            ],
            "closing_tag": "endif",
        },
        "ifchanged": {
            "closing_tag": "endifchanged",
        },
        "spaceless": {
            "closing_tag": "endspaceless",
        },
        "verbatim": {
            "closing_tag": "endverbatim",
        },
        "with": {
            "closing_tag": "endwith",
        },
        "block": {
            "closing_tag": "endblock",
        },
        "comment": {
            "closing_tag": "endcomment",
        },
    },
    "cache": {
        "cache": {
            "closing_tag": "endcache",
        }
    },
    "i18n": {
        "language": {
            "closing_tag": "endlanguage",
        }
    },
    "l10n": {
        "localize": {
            "closing_tag": "endlocalize",
        }
    },
    "tz": {
        "localtime": {
            "closing_tag": "endlocaltime",
        },
        "timezone": {
            "closing_tag": "endtimezone",
        },
    },
}

# Context processors are functions and therefore hard to parse
# Use hardcoded mapping for know context processors.
TEMPLATE_CONTEXT_PROCESSORS = {
    # Django
    "django.template.context_processors.csrf": {
        "csrf_token": None,
    },
    "django.template.context_processors.debug": {
        "debug": None,
        "sql_queries": None,
    },
    "django.template.context_processors.i18n": {
        "LANGUAGES": None,
        "LANGUAGE_CODE": None,
        "LANGUAGE_BIDI": None,
    },
    "django.template.context_processors.tz": {
        "TIME_ZONE": None,
    },
    "django.template.context_processors.static": {
        "STATIC_URL": None,
    },
    "django.template.context_processors.media": {
        "MEDIA_URL": None,
    },
    "django.template.context_processors.request": {
        "request": None,
    },
    # Django: auth
    "django.contrib.auth.context_processors.auth": {
        "user": None,
        "perms": None,
    },
    # Django: messages
    "django.contrib.messages.context_processors.messages": {
        "messages": None,
        "DEFAULT_MESSAGE_LEVELS": None,
    },
    # Wagtail: settings
    "wagtail.contrib.settings.context_processors.settings": {
        # TODO: add fake settings object type with reference to models
        "settings": None,
    },
}

WAGTAIL_PAGE_TEMPLATE_LOOKUP = None


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


def _build_wagtail_page_template_lookup():
    try:
        from wagtail.models import Page
    except ImportError:
        return {}
    wagtail_page_template_lookup = {}
    models = apps.get_models()
    for model in models:
        if issubclass(model, Page):
            wagtail_page_template_lookup[model.template] = {
                "page": model.__module__ + "." + model.__name__,
                "self": model.__module__ + "." + model.__name__,
            }
            if model.context_object_name:
                wagtail_page_template_lookup[model.template][
                    model.context_object_name
                ] = (model.__module__ + "." + model.__name__)
    return wagtail_page_template_lookup


def get_wagtail_page_context(template_name: str) -> dict:
    global WAGTAIL_PAGE_TEMPLATE_LOOKUP
    if WAGTAIL_PAGE_TEMPLATE_LOOKUP is None:
        WAGTAIL_PAGE_TEMPLATE_LOOKUP = _build_wagtail_page_template_lookup()
    return WAGTAIL_PAGE_TEMPLATE_LOOKUP.get(template_name, {})


def get_object_types() -> dict:
    models = apps.get_models()
    object_types = {}
    for model in models:
        model_path = model.__module__ + "." + model.__name__
        object_types[model_path] = {field.name: None for field in model._meta.fields}
    return object_types


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
            "tags": {},
            "filters": {},
        }
    }

    # Collect builtins
    for lib_mod_path in Engine.get_default().builtins:
        lib = importlib.import_module(lib_mod_path).register
        parsed_lib = _parse_library(lib)
        libraries["__builtins__"]["tags"].update(parsed_lib["tags"])
        libraries["__builtins__"]["filters"].update(parsed_lib["filters"])

    # Get Django templatetags
    django_path = inspect.getabsfile(django.templatetags)
    django_mod_files = os.listdir(os.path.dirname(django_path))
    for django_lib in [
        i[:-3] for i in django_mod_files if i.endswith(".py") and i[0] != "_"
    ]:
        try:
            lib = get_installed_libraries()[django_lib]
            lib = importlib.import_module(lib).register
            libraries[django_lib] = _parse_library(lib)
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

            libraries[taglib] = _parse_library(lib)

    # Add node tags
    for lib_name, tags in LIBRARIES_NODE_TAGS.items():
        if lib_name in libraries:
            for tag, options in tags.items():
                if tag in libraries[lib_name]["tags"]:
                    libraries[lib_name]["tags"][tag]["inner_tags"] = options.get(
                        "inner_tags", []
                    )
                    libraries[lib_name]["tags"][tag]["closing_tag"] = options.get(
                        "closing_tag"
                    )

    return libraries


def _parse_library(lib) -> dict:
    return {
        "tags": {
            name: {
                "docs": func.__doc__.strip() if func.__doc__ else "",
            }
            for name, func in lib.tags.items()
        },
        "filters": {
            name: {
                "docs": func.__doc__.strip() if func.__doc__ else "",
            }
            for name, func in lib.filters.items()
        },
    }


def get_templates():
    template_files = {}
    default_engine = Engine.get_default()
    for templates_dir in [
        *default_engine.dirs,
        *get_app_template_dirs("templates"),
    ]:
        for root, dirs, files in os.walk(templates_dir):
            for file in files:
                template_name = os.path.relpath(os.path.join(root, file), templates_dir)

                if template_name in template_files:
                    # Skip already procecesed template
                    # (template have duplicates because other apps can override)
                    continue

                # Get used template (other apps can override templates)
                template_files[template_name] = _parse_template(
                    _get_template_content(default_engine, template_name), template_name
                )
    return template_files


def _get_template_content(engine: Engine, template_name: str):
    for loader in engine.template_loaders:
        for origin in loader.get_template_sources(template_name):
            try:
                return loader.get_contents(origin)
            except Exception:
                pass
    return ""


re_extends = re.compile(r""".*{% ?extends ['"](.*)['"] ?%}.*""")
re_block = re.compile(r".*{% ?block (\w*) ?%}.*")


def get_global_template_context():
    global_context = {}

    # Update object types
    TEMPLATE_CONTEXT_PROCESSORS["django.contrib.auth.context_processors.auth"][
        "user"
    ] = f"{get_user_model().__module__}.{get_user_model().__name__}"

    for context_processor in Engine.get_default().template_context_processors:
        module_path = ".".join(
            [context_processor.__module__, context_processor.__name__]
        )
        if context := TEMPLATE_CONTEXT_PROCESSORS.get(module_path):
            global_context.update(context)
    return global_context


def _parse_template(content, template_name: str) -> dict:
    extends = None
    blocks = set()
    for line in content.splitlines():
        if match := re_extends.match(line):
            extends = match.group(1)
        if match := re_block.match(line):
            blocks.add(match.group(1))

    return {
        "extends": extends,
        "blocks": list(blocks),
        "context": get_wagtail_page_context(
            template_name
        ),  # TODO: Find view/model/contectprocessors
    }


def collect_project_data():
    return {
        "file_watcher_globs": get_file_watcher_globs(),
        "static_files": get_static_files(),
        "urls": get_urls(),
        "libraries": get_libraries(),
        "templates": get_templates(),
        "global_template_context": get_global_template_context(),
        "object_types": get_object_types(),
    }


def get_default_django_settings_module():
    try:
        # Patch django execute to prevent it from running when calling main
        with patch(
            "django.core.management.execute_from_command_line", return_value=None
        ):
            from manage import main

            # Need to run main becuase default env is set in main function
            main()

        return os.getenv("DJANGO_SETTINGS_MODULE")
    except ImportError:
        return ""


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

    if args.project_src:
        sys.path.insert(0, args.project_src)
    else:
        sys.path.insert(0, os.getcwd())

    django_settings_module = (
        args.django_settings_module
        if args.django_settings_module
        else get_default_django_settings_module()
    )
    if args.django_settings_module:
        os.environ.setdefault(
            "DJANGO_SETTINGS_MODULE",
            django_settings_module,
        )

    django.setup()

    print(json.dumps(collect_project_data(), indent=4))
