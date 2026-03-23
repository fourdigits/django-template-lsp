from typing import TypedDict


class CollectorTagPayload(TypedDict, total=False):
    docs: str
    source: str
    inner_tags: list[str]
    closing_tag: str


class CollectorFilterPayload(TypedDict, total=False):
    docs: str
    source: str


class CollectorLibraryPayload(TypedDict):
    tags: dict[str, CollectorTagPayload]
    filters: dict[str, CollectorFilterPayload]


class CollectorVariablePayload(TypedDict, total=False):
    type: str
    docs: str
    value: str


class CollectorTemplatePayload(TypedDict, total=False):
    path: str
    extends: str
    blocks: list[str]
    context: dict[str, CollectorVariablePayload | str]


class CollectorUrlPayload(TypedDict, total=False):
    docs: str
    source: str


class CollectorPayload(TypedDict):
    file_watcher_globs: list[str]
    static_files: list[str]
    urls: dict[str, CollectorUrlPayload]
    libraries: dict[str, CollectorLibraryPayload]
    templates: dict[str, CollectorTemplatePayload]
    global_template_context: dict[str, CollectorVariablePayload | str]


class CollectorPayloadValidationError(ValueError):
    pass


def validate_collector_payload(raw_payload: object) -> CollectorPayload:
    if not isinstance(raw_payload, dict):
        raise CollectorPayloadValidationError("Collector payload must be a dictionary")

    urls_payload = _as_dict(raw_payload.get("urls", {}), key="urls")
    libraries_payload = _as_dict(raw_payload.get("libraries", {}), key="libraries")
    templates_payload = _as_dict(raw_payload.get("templates", {}), key="templates")
    global_context_payload = _as_dict(
        raw_payload.get("global_template_context", {}),
        key="global_template_context",
    )

    payload: CollectorPayload = {
        "file_watcher_globs": _string_list(raw_payload.get("file_watcher_globs", [])),
        "static_files": _string_list(raw_payload.get("static_files", [])),
        "urls": _normalize_urls(urls_payload),
        "libraries": _normalize_libraries(libraries_payload),
        "templates": _normalize_templates(templates_payload),
        "global_template_context": _normalize_context(global_context_payload),
    }
    return payload


def _normalize_urls(payload: dict) -> dict[str, CollectorUrlPayload]:
    urls: dict[str, CollectorUrlPayload] = {}
    for url_name, url_data in payload.items():
        if not isinstance(url_name, str) or not isinstance(url_data, dict):
            continue
        normalized: CollectorUrlPayload = {}
        if isinstance(url_data.get("docs"), str):
            normalized["docs"] = url_data["docs"]
        if isinstance(url_data.get("source"), str):
            normalized["source"] = url_data["source"]
        urls[url_name] = normalized
    return urls


def _normalize_libraries(payload: dict) -> dict[str, CollectorLibraryPayload]:
    libraries: dict[str, CollectorLibraryPayload] = {}
    for lib_name, lib_data in payload.items():
        if not isinstance(lib_name, str) or not isinstance(lib_data, dict):
            continue
        tags_payload = _as_dict(
            lib_data.get("tags", {}), key=f"libraries.{lib_name}.tags"
        )
        filters_payload = _as_dict(
            lib_data.get("filters", {}),
            key=f"libraries.{lib_name}.filters",
        )
        libraries[lib_name] = {
            "tags": _normalize_tags(tags_payload),
            "filters": _normalize_filters(filters_payload),
        }
    return libraries


def _normalize_tags(payload: dict) -> dict[str, CollectorTagPayload]:
    tags: dict[str, CollectorTagPayload] = {}
    for tag_name, tag_data in payload.items():
        if not isinstance(tag_name, str) or not isinstance(tag_data, dict):
            continue
        normalized: CollectorTagPayload = {}
        if isinstance(tag_data.get("docs"), str):
            normalized["docs"] = tag_data["docs"]
        if isinstance(tag_data.get("source"), str):
            normalized["source"] = tag_data["source"]
        if isinstance(tag_data.get("closing_tag"), str):
            normalized["closing_tag"] = tag_data["closing_tag"]
        normalized_inner_tags = _string_list(tag_data.get("inner_tags", []))
        if normalized_inner_tags:
            normalized["inner_tags"] = normalized_inner_tags
        tags[tag_name] = normalized
    return tags


def _normalize_filters(payload: dict) -> dict[str, CollectorFilterPayload]:
    filters: dict[str, CollectorFilterPayload] = {}
    for filter_name, filter_data in payload.items():
        if not isinstance(filter_name, str) or not isinstance(filter_data, dict):
            continue
        normalized: CollectorFilterPayload = {}
        if isinstance(filter_data.get("docs"), str):
            normalized["docs"] = filter_data["docs"]
        if isinstance(filter_data.get("source"), str):
            normalized["source"] = filter_data["source"]
        filters[filter_name] = normalized
    return filters


def _normalize_templates(payload: dict) -> dict[str, CollectorTemplatePayload]:
    templates: dict[str, CollectorTemplatePayload] = {}
    for template_name, template_data in payload.items():
        if not isinstance(template_name, str) or not isinstance(template_data, dict):
            continue
        normalized: CollectorTemplatePayload = {}
        if isinstance(template_data.get("path"), str):
            normalized["path"] = template_data["path"]
        if isinstance(template_data.get("extends"), str):
            normalized["extends"] = template_data["extends"]

        blocks = _string_list(template_data.get("blocks", []))
        if blocks:
            normalized["blocks"] = blocks

        context_payload = _as_dict(
            template_data.get("context", {}),
            key=f"templates.{template_name}.context",
        )
        normalized["context"] = _normalize_context(context_payload)
        templates[template_name] = normalized
    return templates


def _normalize_context(payload: dict) -> dict[str, CollectorVariablePayload | str]:
    context: dict[str, CollectorVariablePayload | str] = {}
    for variable_name, variable_data in payload.items():
        if not isinstance(variable_name, str):
            continue
        if isinstance(variable_data, str):
            context[variable_name] = variable_data
            continue
        if isinstance(variable_data, dict):
            normalized: CollectorVariablePayload = {}
            if isinstance(variable_data.get("type"), str):
                normalized["type"] = variable_data["type"]
            if isinstance(variable_data.get("docs"), str):
                normalized["docs"] = variable_data["docs"]
            if isinstance(variable_data.get("value"), str):
                normalized["value"] = variable_data["value"]
            context[variable_name] = normalized
    return context


def _as_dict(value, *, key: str) -> dict:
    if isinstance(value, dict):
        return value
    raise CollectorPayloadValidationError(
        f"Collector payload key '{key}' must be a dict"
    )


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []
