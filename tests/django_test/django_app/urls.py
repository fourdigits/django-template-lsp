from django.urls import path

from django_app.views import (
    DjangoAppTemplateView,
    DjangoObjectTemplateView,
    django_function_view,
)

app_name = "django_app"


urlpatterns = [
    path("", DjangoAppTemplateView.as_view(), name="index"),
    path("object/", DjangoObjectTemplateView.as_view(), name="object"),
    path("function/", django_function_view, name="function"),
]
