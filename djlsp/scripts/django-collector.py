import argparse
import importlib
import inspect
import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

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
from django.views.generic import View
from django.views.generic.detail import SingleObjectMixin
from django.views.generic.edit import FormMixin
from django.views.generic.list import MultipleObjectMixin

logger = logging.getLogger(__name__)

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
        },
        "blocktrans": {
            "inner_tags": ["plural"],
            "closing_tag": "endblocktrans",
        },
        "blocktranslate": {
            "inner_tags": ["plural"],
            "closing_tag": "endblocktranslate",
        },
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
        "request": "django.http.request.HttpRequest",
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
    # Oscar
    "oscar.core.context_processors.metadata": {
        "shop_name": None,
        "shop_tagline": None,
        "homepage_url": None,
        "language_neutral_url_path": None,
    },
    "oscar.apps.search.context_processors.search_form": {
        "search_form": None,
    },
    "oscar.apps.checkout.context_processors.checkout": {
        "anon_checkout_allowed": None,
    },
    "oscar.apps.communication.notifications.context_processors.notifications": {
        "num_unread_notifications": None,
    },
    # Django CMS
    "cms.context_processors.cms_settings": {
        "cms_menu_renderer": None,
        "CMS_MEDIA_URL": None,
        "CMS_TEMPLATE": None,
    },
}


#######################################################################################
# Index Types
#######################################################################################
@dataclass
class Template:
    path: str = ""
    name: str = ""
    content: str = ""


#######################################################################################
# Index collector
#######################################################################################
class DjangoIndexCollector:
    re_extends = re.compile(r""".*{% ?extends ['"](.*)['"] ?%}.*""")
    re_block = re.compile(r".*{% ?block (\w*) ?%}.*")

    def __init__(self, project_src_path):
        self.project_src_path = project_src_path

        # Index data
        self.file_watcher_globs = []
        self.static_files = []
        self.urls = {}
        self.libraries = {}
        self.templates: dict[str, Template] = {}
        self.global_template_context = {}

    def collect(self):
        self.file_watcher_globs = self.get_file_watcher_globs()
        self.static_files = self.get_static_files()
        self.templates = self.get_templates()
        self.urls = self.get_urls()
        self.libraries = self.get_libraries()
        self.global_template_context = self.get_global_template_context()

        # Third party collectors
        self.collect_for_wagtail()

    def to_json(self):
        return json.dumps(
            {
                "file_watcher_globs": self.file_watcher_globs,
                "static_files": self.static_files,
                "urls": self.urls,
                "libraries": self.libraries,
                "templates": self.templates,
                "global_template_context": self.global_template_context,
            },
            indent=4,
        )

    def get_source_from_type(self, type_):
        def unwrap(func):
            while hasattr(func, "__wrapped__"):
                func = func.__wrapped__
            return func

        type_ = unwrap(type_)

        try:
            source_file = inspect.getsourcefile(type_)
            line = inspect.getsourcelines(type_)[1]
        except Exception as e:
            logger.error(e)
            return ""

        if source_file.startswith(self.project_src_path):
            path = source_file.removeprefix(self.project_src_path).lstrip("/")
            return f"src:{path}:{line}"
        elif source_file.startswith(sys.prefix):
            path = source_file.removeprefix(sys.prefix).lstrip("/")
            return f"env:{path}:{line}"
        return ""

    def get_type_full_name(self, type_):
        return f"{type_.__module__}.{type_.__name__}"

    # File watcher globs
    # ---------------------------------------------------------------------------------
    def get_file_watcher_globs(self):
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

    # Static files
    # ---------------------------------------------------------------------------------
    def get_static_files(self):
        # TODO: Add option to ignore some static folders
        # (like static that is generated with a JS bundler)
        static_paths = []
        for finder in get_finders():
            for path, _ in finder.list(None):
                static_paths.append(path)
        return static_paths

    # Urls
    # ---------------------------------------------------------------------------------
    def get_urls(self):
        try:
            urlpatterns = __import__(settings.ROOT_URLCONF, {}, {}, [""]).urlpatterns
        except Exception:
            return {}

        def recursive_get_views(urlpatterns, namespace=None, pattern=""):
            views = {}
            for p in urlpatterns:
                if isinstance(p, URLPattern):
                    # TODO: Get view path/line and template context
                    if not p.name:
                        name = p.name
                    elif namespace:
                        name = "{0}:{1}".format(namespace, p.name)
                    else:
                        name = p.name

                    if name:
                        callback = getattr(p.callback, "view_class", p.callback)
                        try:
                            self.add_template_context_for_view(callback)
                        except Exception:
                            pass
                        views[name] = {
                            "docs": f"{pattern}{p.pattern}",
                            "source": self.get_source_from_type(callback),
                        }
                elif isinstance(p, URLResolver):
                    try:
                        patterns = p.url_patterns
                    except ImportError:
                        continue
                    if namespace and p.namespace:
                        _namespace = "{0}:{1}".format(namespace, p.namespace)
                    else:
                        _namespace = p.namespace or namespace
                    views.update(
                        recursive_get_views(
                            patterns,
                            namespace=_namespace,
                            pattern=f"{pattern}{p.pattern}",
                        )
                    )
            return views

        return recursive_get_views(urlpatterns)

    # Libaries
    # ---------------------------------------------------------------------------------
    def get_libraries(self):
        libraries = {
            "__builtins__": {
                "tags": {},
                "filters": {},
            }
        }

        # Collect builtins
        for lib_mod_path in Engine.get_default().builtins:
            lib = importlib.import_module(lib_mod_path).register
            parsed_lib = self._parse_library(lib)
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
                libraries[django_lib] = self._parse_library(lib)
            except (InvalidTemplateLibrary, KeyError) as e:
                logger.error(f"Failed to parse django templatetag {django_lib}: {e}")
                continue

        for app_config in apps.get_app_configs():
            app = app_config.name
            try:
                templatetag_mod = __import__(app + ".templatetags", {}, {}, [""])
            except ImportError:
                continue

            try:
                mod_path = inspect.getabsfile(templatetag_mod)
            except TypeError as e:
                logger.error(f"Failed getting path for ({app}) templatetags: {e}")
                continue
            mod_files = os.listdir(os.path.dirname(mod_path))
            tag_files = [i[:-3] for i in mod_files if i.endswith(".py") and i[0] != "_"]

            for taglib in tag_files:
                try:
                    lib = get_installed_libraries()[taglib]
                    lib = importlib.import_module(lib).register
                except (InvalidTemplateLibrary, KeyError) as e:
                    logger.error(f"Failed to parse library ({taglib}): {e}")
                    continue

                libraries[taglib] = self._parse_library(lib)

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

    def _parse_library(self, lib) -> dict:
        return {
            "tags": {
                name: {
                    "docs": func.__doc__.strip() if func.__doc__ else "",
                    "source": self.get_source_from_type(func),
                }
                for name, func in lib.tags.items()
            },
            "filters": {
                name: {
                    "docs": func.__doc__.strip() if func.__doc__ else "",
                    "source": self.get_source_from_type(func),
                }
                for name, func in lib.filters.items()
            },
        }

    # Templates
    # ---------------------------------------------------------------------------------
    def get_templates(self):
        template_files = {}
        default_engine = Engine.get_default()
        for templates_dir in [
            *default_engine.dirs,
            *get_app_template_dirs("templates"),
        ]:
            for root, dirs, files in os.walk(templates_dir):
                for file in files:
                    template_name = os.path.relpath(
                        os.path.join(root, file), templates_dir
                    )

                    if template_name in template_files:
                        # Skip already procecesed template
                        # (template have duplicates because other apps can override)
                        continue

                    # Get used template (other apps can override templates)
                    template_files[template_name] = self._parse_template(
                        self._get_template(default_engine, template_name),
                    )
        return template_files

    def add_template_context_for_view(self, view):
        if not issubclass(view, View):
            # Ensure only class-based views (CBVs) are allowed; function-based
            # views (FBVs) are not supported
            return

        view_obj = view(request=MagicMock())

        try:
            template_name = view_obj.get_template_names()[0]
        except Exception:
            template_name = getattr(view, "template_name", None)

        if template_name in self.templates:
            if issubclass(view, SingleObjectMixin) and hasattr(view, "model"):
                context = {"object": self.get_type_full_name(view.model)}
                try:
                    context_name = view_obj.get_context_object_name(view.model)
                    if context_name:
                        context[context_name] = context["object"]
                except Exception:
                    pass
                self.templates[template_name]["context"].update(context)
            if issubclass(view, MultipleObjectMixin):
                try:
                    paginator = self.get_type_full_name(view.paginator_class)
                except Exception:
                    paginator = "django.core.paginator.Paginator"

                self.templates[template_name]["context"].update(
                    {
                        "paginator": paginator,
                        "page_obj": "django.core.paginator.Page",
                        "is_paginated": "bool",
                        "object_list": "django.db.models.QuerySet",
                    }
                )
            if issubclass(view, FormMixin) and hasattr(view, "form_class"):
                self.templates[template_name]["context"].update(
                    {"form": self.get_type_full_name(view.form_class)}
                )

    def _parse_template(self, template: Template) -> dict:
        extends = None
        blocks = set()
        for line in template.content.splitlines():
            if match := self.re_extends.match(line):
                extends = match.group(1)
            if match := self.re_block.match(line):
                blocks.add(match.group(1))

        path = ""
        if template.path.startswith(self.project_src_path):
            path = (
                f"src:{template.path.removeprefix(self.project_src_path).lstrip('/')}"
            )
        elif template.path.startswith(sys.prefix):
            path = f"env:{template.path.removeprefix(sys.prefix).lstrip('/')}"

        return {
            "path": path,
            "extends": extends,
            "blocks": list(blocks),
            "context": {},
        }

    def _get_template(self, engine: Engine, template_name: str) -> Template:
        for loader in engine.template_loaders:
            for origin in loader.get_template_sources(template_name):
                try:
                    return Template(
                        path=str(origin),
                        name=template_name,
                        content=loader.get_contents(origin),
                    )
                except Exception:
                    pass
        return Template(name=template_name)

    # Global context
    # ---------------------------------------------------------------------------------
    def get_global_template_context(self):
        global_context = {
            # builtins
            "True": None,
            "False": None,
            "None": None,
        }

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

    # Third party: Wagtail
    # ---------------------------------------------------------------------------------
    def collect_for_wagtail(self):
        try:
            from wagtail.models import Page
        except ImportError:
            return
        for model in apps.get_models():
            if issubclass(model, Page) and model.template in self.templates:
                self.templates[model.template]["context"].update(
                    {
                        "page": model.__module__ + "." + model.__name__,
                        "self": model.__module__ + "." + model.__name__,
                    }
                )
                if model.context_object_name:
                    self.templates[model.template]["context"][
                        model.context_object_name
                    ] = (model.__module__ + "." + model.__name__)


#######################################################################################
# CLI
#######################################################################################
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

    project_src_path = args.project_src if args.project_src else os.getcwd()
    sys.path.insert(0, project_src_path)

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

    # Enable error logging to stderr
    logging.basicConfig(
        level=logging.ERROR,
        format="%(message)s",
        handlers=[logging.StreamHandler(sys.stderr)],
    )

    django.setup()

    collector = DjangoIndexCollector(project_src_path)
    collector.collect()

    print(collector.to_json())
