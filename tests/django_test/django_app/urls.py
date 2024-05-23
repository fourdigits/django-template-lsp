from django.http import HttpResponse
from django.urls import path

app_name = "django_app"


urlpatterns = [
    path("", lambda request: HttpResponse(""), name="index"),
]
