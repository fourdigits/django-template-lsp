"""Wagtail collector plugin for django-template-lsp.

Adds Wagtail ``Page`` model context variables (``page``, ``self``, and any
custom ``context_object_name``) to the templates they are bound to.

This plugin is registered as a built-in ``djlsp.collector_plugins`` entry
point and runs automatically when ``wagtail`` is importable in the Django
project's Python environment.
"""

from djlsp.plugins import CollectorPlugin


class WagtailCollectorPlugin(CollectorPlugin):
    def collect(self, collector) -> None:
        try:
            from wagtail.models import Page
        except ImportError:
            return

        from django.apps import apps

        for model in apps.get_models():
            if not issubclass(model, Page):
                continue
            if model.template not in collector.templates:
                continue
            collector.templates[model.template]["context"].update(
                {
                    "page": model.__module__ + "." + model.__name__,
                    "self": model.__module__ + "." + model.__name__,
                }
            )
            if model.context_object_name:
                collector.templates[model.template]["context"][
                    model.context_object_name
                ] = model.__module__ + "." + model.__name__
