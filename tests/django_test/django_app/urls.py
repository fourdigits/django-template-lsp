from django.urls import path

from django_app.views import DjangoAppTemplateView

app_name = "django_app"


urlpatterns = [
    path("", DjangoAppTemplateView.as_view(), name="index"),
]
