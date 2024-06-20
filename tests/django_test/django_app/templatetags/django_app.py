from django import template

register = template.Library()


@register.simple_tag
def django_app_tag(value):
    """Docs for tag"""
    pass


@register.filter
def django_app_filter(value):
    """Docs for filter"""
    pass
