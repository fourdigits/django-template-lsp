from django.urls import include, path

urlpatterns = [path("", include("django_app.urls", namespace="django_app"))]
