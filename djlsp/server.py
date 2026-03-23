import logging
import os
import threading
from functools import cached_property

import jedi
from lsprotocol.types import (
    COMPLETION_ITEM_RESOLVE,
    INITIALIZE,
    TEXT_DOCUMENT_CODE_ACTION,
    TEXT_DOCUMENT_COMPLETION,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_DID_CHANGE,
    TEXT_DOCUMENT_DID_OPEN,
    TEXT_DOCUMENT_DID_SAVE,
    TEXT_DOCUMENT_HOVER,
    WORKSPACE_DID_CHANGE_WATCHED_FILES,
    CodeActionParams,
    CompletionItem,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    DefinitionParams,
    DidChangeTextDocumentParams,
    DidChangeWatchedFilesParams,
    DidOpenTextDocumentParams,
    DidSaveTextDocumentParams,
    HoverParams,
    InitializeParams,
)
from pygls.server import LanguageServer

from djlsp import __version__
from djlsp.collector_payload import (
    CollectorPayloadValidationError,
    validate_collector_payload,
)
from djlsp.constants import FALLBACK_DJANGO_DATA
from djlsp.index import WorkspaceIndex
from djlsp.parser import clear_completions_cache
from djlsp.plugins import (
    CoreTemplatePlugin,
    DjangoUrlsPlugin,
    PluginContext,
    PluginManager,
)
from djlsp.services import (
    DJANGO_COLLECTOR_SCRIPT_PATH,
    CacheService,
    CollectorRequest,
    CollectorRunnerService,
    SubprocessRunner,
    VersionCheckService,
    WatcherService,
)

logger = logging.getLogger(__name__)

DEFAULT_ENV_DIRECTORIES = [
    "env",
    ".env",
    "venv",
    ".venv",
]


class DjangoTemplateLanguageServer(LanguageServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.env_directories = DEFAULT_ENV_DIRECTORIES
        self.docker_compose_file = "docker-compose.yml"
        self.docker_compose_service = "django"
        self.django_settings_module = ""
        self.version_check = True
        self.cache = False
        self.workspace_index = WorkspaceIndex()
        self.workspace_index.update(FALLBACK_DJANGO_DATA)
        self.jedi_project = jedi.Project(".")
        self.is_initialized = False
        self.command_runner = SubprocessRunner()
        self.cache_service = CacheService(
            collector_script_path=DJANGO_COLLECTOR_SCRIPT_PATH
        )
        self.collector_runner = CollectorRunnerService(
            command_runner=self.command_runner,
            cache_service=self.cache_service,
            collector_script_path=DJANGO_COLLECTOR_SCRIPT_PATH,
        )
        self.watcher_service = WatcherService()
        self.version_check_service = VersionCheckService()
        self.plugin_manager = PluginManager(
            plugins=[CoreTemplatePlugin(), DjangoUrlsPlugin()]
        )

    @cached_property
    def project_src_path(self):
        """Root path to src files, auto detect based on manage.py file"""
        for name in os.listdir(self.workspace.root_path):
            src_path = os.path.join(self.workspace.root_path, name)
            if os.path.exists(os.path.join(src_path, "manage.py")):
                return src_path
        return self.workspace.root_path

    @cached_property
    def project_env_path(self):
        for env_dir in self.env_directories:
            env_path = (
                env_dir
                if os.path.isabs(env_dir)
                else os.path.join(self.workspace.root_path, env_dir)
            )
            if os.path.exists(os.path.join(env_path, "bin", "python")):
                return os.path.join(env_path)

    @property
    def docker_compose_path(self):
        return os.path.join(self.workspace.root_path, self.docker_compose_file)

    def set_initialization_options(self, options: dict):
        env_directories = options.get("env_directories", self.env_directories)
        self.env_directories = (
            list(map(str, env_directories))
            if isinstance(env_directories, list)
            else self.env_directories
        )
        self.docker_compose_file = options.get(
            "docker_compose_file", self.docker_compose_file
        )
        self.docker_compose_service = options.get(
            "docker_compose_service", self.docker_compose_service
        )
        self.django_settings_module = options.get(
            "django_settings_module", self.django_settings_module
        )
        self.version_check = options.get("version_check", self.version_check)
        self.cache = options.get("cache", self.cache)
        self.plugin_manager.configure(options=options.get("plugins"))

    def check_version(self):
        if latest_version := self.version_check_service.check_for_upgrade(__version__):
            self.show_message(
                f"There is a new version for djlsp ({latest_version})"
                ", upgrade with `pipx upgrade django-template-lsp`"
            )

    def check_version_async(self):
        if not self.version_check:
            return
        threading.Thread(target=self.check_version, daemon=True).start()

    def get_django_data(self, update_file_watcher=True, changed_kinds=None):
        self.workspace_index.src_path = self.project_src_path
        self.workspace_index.env_path = self.project_env_path
        self.jedi_project = jedi.Project(
            path=self.project_src_path, environment_path=self.project_env_path
        )

        if changed_kinds:
            logger.debug(
                "File watcher triggered recollect for change kinds: %s", changed_kinds
            )

        result = self.collector_runner.collect(
            CollectorRequest(
                workspace_root=self.workspace.root_path,
                project_src_path=self.project_src_path,
                project_env_path=self.project_env_path,
                docker_compose_path=self.docker_compose_path,
                django_settings_module=self.django_settings_module,
                docker_compose_file=self.docker_compose_file,
                docker_compose_service=self.docker_compose_service,
                cache=self.cache,
            )
        )
        django_data = result.django_data
        has_applied_payload = False

        if django_data:
            try:
                validated_payload = validate_collector_payload(django_data)
            except CollectorPayloadValidationError as exc:
                logger.error("Invalid collector payload: %s", exc)
                validated_payload = None

            if not validated_payload:
                logger.info("Could not apply collected project Django data")
            else:
                self.workspace_index.update(validated_payload)
                has_applied_payload = True
                logger.info(
                    "Collected project Django data%s:",
                    f" from {result.source}" if result.source else "",
                )
                logger.info(f" - Libraries: {len(validated_payload['libraries'])}")
                logger.info(f" - Templates: {len(validated_payload['templates'])}")
                logger.info(
                    f" - Static files: {len(validated_payload['static_files'])}"
                )
                logger.info(f" - Urls: {len(validated_payload['urls'])}")
                logger.info(
                    " - Global context: %s",
                    len(validated_payload["global_template_context"]),
                )

        if not has_applied_payload:
            logger.info("Could not collect project Django data")
        if not has_applied_payload and not self.is_initialized:
            # This message is only shown during startup. On save, a full
            # collect occurs, which may involve partial edits.  To avoid
            # spamming the user with messages, we provide feedback only
            # at startup.
            self.show_message(
                "Failed to collect project-specific Django data. Falling back to default Django completions."  # noqa: E501
            )

        if update_file_watcher and (
            registration := self.watcher_service.build_registration(
                self.workspace_index.file_watcher_globs
            )
        ):
            self.register_capability(registration)


server = DjangoTemplateLanguageServer("django-template-lsp", __version__)


def _plugin_context(ls: DjangoTemplateLanguageServer, uri: str) -> PluginContext:
    return PluginContext(
        workspace_index=ls.workspace_index,
        jedi_project=ls.jedi_project,
        document=ls.workspace.get_document(uri),
    )


def _publish_plugin_diagnostics(ls: DjangoTemplateLanguageServer, uri: str):
    try:
        context = _plugin_context(ls, uri)
        diagnostics = ls.plugin_manager.diagnostics(context)
        ls.publish_diagnostics(uri, diagnostics)
    except Exception as e:
        logger.error(e)


@server.feature(INITIALIZE)
def initialized(ls: DjangoTemplateLanguageServer, params: InitializeParams):
    logger.info(f"COMMAND: {INITIALIZE}")
    logger.debug(f"OPTIONS: {params.initialization_options}")
    if params.initialization_options:
        ls.set_initialization_options(params.initialization_options)
    ls.check_version_async()
    ls.get_django_data()
    ls.is_initialized = True


@server.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(
        trigger_characters=[" ", "|", "'", '"', "."], resolve_provider=True
    ),
)
def completions(ls: DjangoTemplateLanguageServer, params: CompletionParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_COMPLETION}")
    logger.debug(f"PARAMS: {params}")

    clear_completions_cache()
    try:
        context = _plugin_context(ls, params.text_document.uri)
        return CompletionList(
            is_incomplete=False,
            items=ls.plugin_manager.completions(
                context,
                line=params.position.line,
                character=params.position.character,
            ),
        )
    except Exception as e:
        logger.error(e)
        return None


@server.feature(COMPLETION_ITEM_RESOLVE)
def completion_item_resolve(ls: DjangoTemplateLanguageServer, item: CompletionItem):
    logger.info(f"COMMAND: {COMPLETION_ITEM_RESOLVE}")
    logger.debug(f"PARAMS: {item}")

    return ls.plugin_manager.resolve_completion(item)


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: DjangoTemplateLanguageServer, params: HoverParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_HOVER}")
    logger.debug(f"PARAMS: {params}")
    try:
        context = _plugin_context(ls, params.text_document.uri)
        return ls.plugin_manager.hover(
            context,
            line=params.position.line,
            character=params.position.character,
        )
    except Exception as e:
        logger.error(e)
        return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
def goto_definition(ls: DjangoTemplateLanguageServer, params: DefinitionParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_DEFINITION}")
    logger.debug(f"PARAMS: {params}")
    try:
        context = _plugin_context(ls, params.text_document.uri)
        return ls.plugin_manager.definition(
            context,
            line=params.position.line,
            character=params.position.character,
        )
    except Exception as e:
        logger.error(e)
        return None


@server.feature(TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: DjangoTemplateLanguageServer, params: DidOpenTextDocumentParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_DID_OPEN}")
    logger.debug(f"PARAMS: {params}")
    _publish_plugin_diagnostics(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: DjangoTemplateLanguageServer, params: DidChangeTextDocumentParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_DID_CHANGE}")
    logger.debug(f"PARAMS: {params}")
    _publish_plugin_diagnostics(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: DjangoTemplateLanguageServer, params: DidSaveTextDocumentParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_DID_SAVE}")
    logger.debug(f"PARAMS: {params}")
    _publish_plugin_diagnostics(ls, params.text_document.uri)


@server.feature(TEXT_DOCUMENT_CODE_ACTION)
def code_action(ls: DjangoTemplateLanguageServer, params: CodeActionParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_CODE_ACTION}")
    logger.debug(f"PARAMS: {params}")
    try:
        context = _plugin_context(ls, params.text_document.uri)
        return ls.plugin_manager.code_actions(context, params=params)
    except Exception as e:
        logger.error(e)
        return None


@server.thread()
@server.feature(WORKSPACE_DID_CHANGE_WATCHED_FILES)
def files_changed(
    ls: DjangoTemplateLanguageServer, params: DidChangeWatchedFilesParams
):
    logger.info(f"COMMAND: {WORKSPACE_DID_CHANGE_WATCHED_FILES}")
    logger.debug(f"PARAMS: {params}")
    ls.watcher_service.schedule_collection(
        lambda change_kinds: ls.get_django_data(changed_kinds=change_kinds),
        params.changes,
    )
