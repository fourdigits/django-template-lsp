from djlsp.ast_context_collector import AstContextCollector


class AstCollectorViewFixture:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["direct_key"] = 1
        ctx = context
        ctx.update({"update_key": 2})
        ctx.update(kwarg_key=3)
        extra = {"alias_key": 4}
        context.update(extra)
        merged = {"dict_left": 1} | {"dict_right": 2}
        context.update(merged)
        context |= {"merge_key": 3}
        return {"return_left": 1, **context, "return_right": 2}


def render(_request, _template_name, _context):
    return None


def ast_collector_function_fixture(request):
    context = {"fbv_assignment": 1}
    alias = {"fbv_alias": 2}
    return render(request, "fixture.html", {**context, **alias, "fbv_return": 3})


def test_ast_context_collector_extracts_supported_context_patterns():
    keys = AstContextCollector().extract_context_keys(AstCollectorViewFixture)

    assert keys == {
        "direct_key",
        "update_key",
        "kwarg_key",
        "alias_key",
        "dict_left",
        "dict_right",
        "merge_key",
        "return_left",
        "return_right",
    }


def test_ast_context_collector_extracts_supported_render_patterns():
    results = AstContextCollector().extract_function_render_contexts(
        ast_collector_function_fixture
    )

    assert len(results) == 1
    assert results[0].template_name == "fixture.html"
    assert results[0].context_keys == {
        "fbv_assignment",
        "fbv_alias",
        "fbv_return",
    }
