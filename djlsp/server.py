from lsprotocol.types import (TEXT_DOCUMENT_COMPLETION,
                              TEXT_DOCUMENT_DID_CHANGE, CompletionItem,
                              CompletionList, CompletionOptions,
                              CompletionParams, DidChangeTextDocumentParams)
from pygls.server import LanguageServer

from djlsp import __version__
from djlsp.completion import get_completions

server = LanguageServer("django-template-lsp", __version__)


@server.feature(
    TEXT_DOCUMENT_COMPLETION, CompletionOptions(trigger_characters=[" ", "|"])
)
def completions(params: CompletionParams):
    items = []
    document = server.workspace.get_document(params.text_document.uri)
    line_fragment = document.lines[params.position.line][: params.position.character]
    for completion in get_completions(line_fragment):
        items.append(CompletionItem(label=completion))
    return CompletionList(is_incomplete=False, items=items)
