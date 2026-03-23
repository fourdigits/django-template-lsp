from django.contrib.auth import get_user_model
from django.shortcuts import render
from django.views.generic import TemplateView
from django.views.generic.detail import SingleObjectMixin


class DjangoAppTemplateView(TemplateView):
    template_name = "django_app.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["from_ast_assignment"] = "assigned"
        context.update({"from_ast_update": "updated"})
        context |= {"from_ast_merge": "merged"}
        return context


class DjangoObjectTemplateView(SingleObjectMixin, TemplateView):
    template_name = "django_app.html"
    model = get_user_model()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["object"] = "ast-object"
        return context


def django_function_view(request):
    context = {"from_fbv_assignment": "assigned"}
    extra = {"from_fbv_alias": "alias"}
    return render(
        request,
        "django_app.html",
        {**context, **extra, "from_fbv_return": "return"},
    )
