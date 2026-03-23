from django.views.generic import TemplateView


class DjangoAppTemplateView(TemplateView):
    template_name = "django_app.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["from_ast_assignment"] = "assigned"
        context.update({"from_ast_update": "updated"})
        context |= {"from_ast_merge": "merged"}
        return context
