import json
import logging
import os
import shutil
import subprocess
import uuid

from lsprotocol.types import (
    INITIALIZE,
    TEXT_DOCUMENT_COMPLETION,
    WORKSPACE_DID_CHANGE_WATCHED_FILES,
    CompletionItem,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    DidChangeWatchedFilesParams,
    DidChangeWatchedFilesRegistrationOptions,
    FileSystemWatcher,
    InitializeParams,
    Registration,
    RegistrationParams,
)
from pygls.server import LanguageServer

from djlsp import __version__
from djlsp.constants import FALLBACK_DJANGO_DATA
from djlsp.index import WorkspaceIndex
from djlsp.parser import TemplateParser

logger = logging.getLogger(__name__)


DJANGO_COLLECTOR_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "scripts",
    "django-collector.py",
)


class DjangoTemplateLanguageServer(LanguageServer):
    ENV_DIRECTORIES = [
        "env",
        ".env",
        "venv",
        ".venv",
    ]

    def __init__(self, *args):
        super().__init__(*args)
        self.file_watcher_id = str(uuid.uuid4())
        self.current_file_watcher_globs = []
        self.docker_compose_file = "docker-compose.yml"
        self.docker_compose_service = "django"
        self.django_settings_module = ""
        self.workspace_index = WorkspaceIndex()
        self.workspace_index.update(FALLBACK_DJANGO_DATA)

    def set_initialization_options(self, options: dict):
        self.docker_compose_file = options.get(
            "docker_compose_file", self.docker_compose_file
        )
        self.docker_compose_service = options.get(
            "docker_compose_service", self.docker_compose_service
        )
        self.django_settings_module = options.get(
            "django_settings_module", self.django_settings_module
        )

    def set_file_watcher_capability(self):
        logger.info(
            f"Update file watcher patterns to: {self.current_file_watcher_globs}"
        )
        self.register_capability(
            RegistrationParams(
                registrations=[
                    Registration(
                        id=self.file_watcher_id,
                        method=WORKSPACE_DID_CHANGE_WATCHED_FILES,
                        register_options=DidChangeWatchedFilesRegistrationOptions(
                            watchers=[
                                FileSystemWatcher(glob_pattern=glob_pattern)
                                for glob_pattern in self.current_file_watcher_globs
                            ]
                        ),
                    )
                ]
            )
        )

    def get_django_data(self):
        if self._has_valid_docker_service():
            django_data = self._get_django_data_from_docker()
        elif python_path := self._get_python_path():
            django_data = self._get_django_data_from_python_path(python_path)
        else:
            django_data = None

        if django_data:
            # TODO: Maybe validate data
            self.workspace_index.update(django_data)
            logger.info("Collected project Django data:")
            logger.info(f" - Libraries: {len(django_data['libraries'])}")
            logger.info(f" - Templates: {len(django_data['templates'])}")
            logger.info(f" - Static files: {len(django_data['static_files'])}")
            logger.info(f" - Urls: {len(django_data['urls'])}")
            logger.info(
                f" - Global context: {len(django_data['global_template_context'])}"
            )
        else:
            logger.info("Could not collect Django data")

        if set(self.workspace_index.file_watcher_globs) != set(
            self.current_file_watcher_globs
        ):
            self.current_file_watcher_globs = self.workspace_index.file_watcher_globs
            self.set_file_watcher_capability()

    def _get_python_path(self):
        for env_dir in self.ENV_DIRECTORIES:
            env_python_path = os.path.join(
                self.workspace.root_path, env_dir, "bin", "python"
            )
            if os.path.exists(env_python_path):
                return env_python_path
        return shutil.which("python3")

    def _get_django_data_from_python_path(self, python_path):
        logger.info(f"Collection django data from local python path: {python_path}")
        project_src = self.workspace.root_path
        if os.path.isdir(os.path.join(project_src, "src")):
            project_src = os.path.join(project_src, "src")

        logger.info(f" - For project path: {project_src}")

        try:
            return json.loads(
                subprocess.check_output(
                    filter(
                        None,
                        [
                            python_path,
                            DJANGO_COLLECTOR_SCRIPT_PATH,
                            (
                                f"--django-settings-module={self.django_settings_module}"  # noqa: E501
                                if self.django_settings_module
                                else None
                            ),
                            f"--project-src={project_src}",
                        ],
                    )
                ).decode()
            )
        except Exception as e:
            logger.error(e)
            return False

    def _has_valid_docker_service(self):
        docker_compose_path = os.path.join(
            self.workspace.root_path, self.docker_compose_file
        )
        if os.path.exists(docker_compose_path):
            services = (
                subprocess.check_output(
                    [
                        "docker",
                        "compose",
                        f"--file={docker_compose_path}",
                        "config",
                        "--services",
                    ]
                )
                .decode()
                .splitlines()
            )
            return self.docker_compose_service in services
        return False

    def _get_django_data_from_docker(self):
        logger.info(
            f"Collecting django data from docker {self.docker_compose_file}:{self.docker_compose_service}"  # noqa: E501
        )
        docker_compose_path = os.path.join(
            self.workspace.root_path, self.docker_compose_file
        )

        try:
            return json.loads(
                subprocess.check_output(
                    list(
                        filter(
                            None,
                            [
                                "docker",
                                "compose",
                                f"--file={docker_compose_path}",
                                "run",
                                "--rm",
                                f"--volume={DJANGO_COLLECTOR_SCRIPT_PATH}:/django-collector.py",  # noqa: E501
                                self.docker_compose_service,
                                "python",
                                "/django-collector.py",
                                (
                                    f"--django-settings-module={self.django_settings_module}"  # noqa: E501
                                    if self.django_settings_module
                                    else None
                                ),
                            ],
                        )
                    )
                ).decode()
            )
        except Exception as e:
            logger.error(e)
            return False


server = DjangoTemplateLanguageServer("django-template-lsp", __version__)


@server.feature(INITIALIZE)
def initialized(ls: DjangoTemplateLanguageServer, params: InitializeParams):
    logger.info(f"COMMAND: {INITIALIZE}")
    logger.debug(f"OPTIONS: {params.initialization_options}")
    if params.initialization_options:
        ls.set_initialization_options(params.initialization_options)
    ls.get_django_data()


@server.feature(
    TEXT_DOCUMENT_COMPLETION, CompletionOptions(trigger_characters=[" ", "|", "'"])
)
def completions(ls: DjangoTemplateLanguageServer, params: CompletionParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_COMPLETION}")
    logger.debug(f"PARAMS: {params}")
    items = []
    document = server.workspace.get_document(params.text_document.uri)
    template = TemplateParser(ls.workspace_index, document)
    for completion in template.completions(
        params.position.line, params.position.character
    ):
        items.append(CompletionItem(label=completion))
    return CompletionList(is_incomplete=False, items=items)


@server.feature(WORKSPACE_DID_CHANGE_WATCHED_FILES)
def files_changed(
    ls: DjangoTemplateLanguageServer, params: DidChangeWatchedFilesParams
):
    logger.info(f"COMMAND: {WORKSPACE_DID_CHANGE_WATCHED_FILES}")
    logger.debug(f"PARAMS: {params}")
    # TODO: Do partial collect based on changed file type
    ls.get_django_data()
