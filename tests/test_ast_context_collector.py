from djlsp.ast_context_collector import AstContextCollector


class AstCollectorViewFixture:
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["direct_key"] = 1
        ctx = context
        ctx.update({"update_key": 2})
        context |= {"merge_key": 3}
        return context | {"return_merge_key": 4}


def test_ast_context_collector_extracts_supported_context_patterns():
    keys = AstContextCollector().extract_context_keys(AstCollectorViewFixture)

    assert keys == {"direct_key", "update_key", "merge_key", "return_merge_key"}
