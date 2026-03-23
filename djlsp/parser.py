import jedi
from pygls.workspace import TextDocument

from djlsp.completion import (
    CompletionMixin,
)
from djlsp.completion import (
    clear_completions_cache as _clear_completions_cache,
)
from djlsp.context_inference import ContextInferenceMixin
from djlsp.definition import DefinitionMixin
from djlsp.hover import HoverMixin
from djlsp.index import WorkspaceIndex

clear_completions_cache = _clear_completions_cache


class TemplateParser(
    CompletionMixin,
    HoverMixin,
    DefinitionMixin,
    ContextInferenceMixin,
):
    def __init__(
        self,
        workspace_index: WorkspaceIndex,
        jedi_project: jedi.Project,
        document: TextDocument,
    ):
        self.workspace_index = workspace_index
        self.jedi_project = jedi_project
        self.document = document
