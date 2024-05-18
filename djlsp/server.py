from lsprotocol.types import (
    TEXT_DOCUMENT_COMPLETION,
    CompletionItem,
    CompletionList,
    CompletionOptions,
    CompletionParams,
)
from pygls.server import LanguageServer

from djlsp import __version__
from djlsp.parser import TemplateParser

server = LanguageServer("django-template-lsp", __version__)


@server.feature(
    TEXT_DOCUMENT_COMPLETION, CompletionOptions(trigger_characters=[" ", "|", "'"])
)
def completions(params: CompletionParams):
    items = []
    document = server.workspace.get_document(params.text_document.uri)
    template = TemplateParser(document)
    for completion in template.completions(
        params.position.line, params.position.character
    ):
        items.append(CompletionItem(label=completion))
    return CompletionList(is_incomplete=False, items=items)
