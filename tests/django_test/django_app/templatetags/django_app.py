from django import template

register = template.Library()


@register.simple_tag
def django_app_tag(value):
    pass


@register.filter
def django_app_filter(value):
    pass
