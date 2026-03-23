import pytest

from djlsp.collector_payload import (
    CollectorPayloadValidationError,
    validate_collector_payload,
)


def test_validate_collector_payload_rejects_non_dict():
    with pytest.raises(CollectorPayloadValidationError):
        validate_collector_payload(["invalid"])


def test_validate_collector_payload_rejects_invalid_required_top_level_types():
    with pytest.raises(CollectorPayloadValidationError):
        validate_collector_payload(
            {
                "file_watcher_globs": [],
                "static_files": [],
                "urls": {},
                "libraries": {},
                "templates": [],
                "global_template_context": {},
            }
        )


def test_validate_collector_payload_normalizes_known_shape():
    payload = validate_collector_payload(
        {
            "file_watcher_globs": ["**/templates/**", 123],
            "static_files": ["app.js", None],
            "urls": {
                "website:home": {"docs": "Homepage", "source": "src:urls.py:1"},
                1: {"docs": "ignored"},
            },
            "libraries": {
                "website": {
                    "tags": {
                        "hello": {
                            "docs": "tag docs",
                            "inner_tags": ["else", None],
                            "closing_tag": "endhello",
                        }
                    },
                    "filters": {"money": {"docs": "money docs", "source": 5}},
                }
            },
            "templates": {
                "base.html": {
                    "path": "src:templates/base.html",
                    "context": {
                        "blog": {"type": "Blog", "docs": "context docs"},
                        "author": "Author",
                        "ignored": 42,
                    },
                }
            },
            "global_template_context": {
                "request": {"type": "HttpRequest"},
                "user": "User",
            },
        }
    )

    assert payload["file_watcher_globs"] == ["**/templates/**"]
    assert payload["static_files"] == ["app.js"]
    assert payload["urls"]["website:home"]["source"] == "src:urls.py:1"
    assert payload["libraries"]["website"]["tags"]["hello"]["inner_tags"] == ["else"]
    assert payload["libraries"]["website"]["filters"]["money"] == {"docs": "money docs"}
    assert payload["templates"]["base.html"]["context"]["author"] == "Author"
    assert payload["global_template_context"]["request"] == {"type": "HttpRequest"}
