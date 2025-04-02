import glob
import hashlib
import http.client
import json
import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from functools import cached_property

import jedi
from lsprotocol.types import (
    INITIALIZE,
    TEXT_DOCUMENT_COMPLETION,
    COMPLETION_ITEM_RESOLVE,
    TEXT_DOCUMENT_DEFINITION,
    TEXT_DOCUMENT_HOVER,
    WORKSPACE_DID_CHANGE_WATCHED_FILES,
    CompletionItem,
    CompletionList,
    CompletionOptions,
    CompletionParams,
    DefinitionParams,
    DidChangeWatchedFilesParams,
    DidChangeWatchedFilesRegistrationOptions,
    FileSystemWatcher,
    HoverParams,
    InitializeParams,
    Registration,
    RegistrationParams,
)
from pygls.server import LanguageServer

from djlsp import __version__
from djlsp.constants import FALLBACK_DJANGO_DATA
from djlsp.index import WorkspaceIndex
from djlsp.parser import TemplateParser, _MOST_RECENT_COMPLETIONS

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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.file_watcher_id = str(uuid.uuid4())
        self.current_file_watcher_globs = []
        self.docker_compose_file = "docker-compose.yml"
        self.docker_compose_service = "django"
        self.django_settings_module = ""
        self.cache = False
        self.workspace_index = WorkspaceIndex()
        self.workspace_index.update(FALLBACK_DJANGO_DATA)
        self.jedi_project = jedi.Project(".")
        self.is_initialized = False

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
        for env_dir in self.ENV_DIRECTORIES:
            if os.path.exists(
                os.path.join(self.workspace.root_path, env_dir, "bin", "python")
            ):
                return os.path.join(self.workspace.root_path, env_dir)

    @property
    def docker_compose_path(self):
        return os.path.join(self.workspace.root_path, self.docker_compose_file)

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
        self.cache = options.get("cache", self.cache)

    def check_version(self):
        try:
            connection = http.client.HTTPSConnection("pypi.org", timeout=1)
            connection.request(
                "GET",
                "/pypi/django-template-lsp/json",
                headers={"User-Agent": "Python/3"},
            )
            response = connection.getresponse()
            if response.status == 200:
                latest_version = (
                    json.loads(response.read().decode("utf-8"))
                    .get("info", {})
                    .get("version", "0.0.0")
                )
                if self._parse_version(latest_version) > self._parse_version(
                    __version__
                ):
                    self.show_message(
                        f"There is a new version for djlsp ({latest_version})"
                        ", upgrade with `pipx upgrade django-template-lsp`"
                    )
        except Exception as e:
            logger.error(f"Could not check latest version: {e}")

    def _parse_version(self, version):
        # Split the version into major, minor, and patch components
        return tuple(map(int, str(version).split(".")))

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

    def get_django_data(self, update_file_watcher=True):
        self.workspace_index.src_path = self.project_src_path
        self.workspace_index.env_path = self.project_env_path
        self.jedi_project = jedi.Project(
            path=self.project_src_path, environment_path=self.project_env_path
        )

        loaded_from_cache = False
        if self.cache and (django_data := self._get_django_data_from_cache()):
            loaded_from_cache = True
        elif self.project_env_path:
            django_data = self._get_django_data_from_python_path(
                os.path.join(self.project_env_path, "bin", "python")
            )
        elif self._has_valid_docker_service():
            django_data = self._get_django_data_from_docker()
        elif python_path := shutil.which("python3"):
            # Try getting data with global python installtion
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
            logger.info("Could not collect project Django data")
            if not self.is_initialized:
                # This message is only shown during startup. On save, a full
                # collect occurs, which may involve partial edits.  To avoid
                # spamming the user with messages, we provide feedback only
                # at startup.
                self.show_message(
                    "Failed to collect project-specific Django data. Falling back to default Django completions."  # noqa: E501
                )

        if update_file_watcher and set(self.workspace_index.file_watcher_globs) != set(
            self.current_file_watcher_globs
        ):
            self.current_file_watcher_globs = self.workspace_index.file_watcher_globs
            self.set_file_watcher_capability()

        if self.cache and not loaded_from_cache and django_data:
            self._store_django_data_to_cache(django_data)

    def _get_django_data_from_cache(self):
        cache_path = self._get_cache_location()
        if not os.path.isfile(cache_path):
            return None

        logger.debug(f"Found cachefile: {cache_path}")
        try:
            with open(cache_path, "r") as f:
                django_data = json.load(f)
        except Exception:
            logger.warning(f"Cannot read cachefile: {cache_path}", exc_info=True)
            return None

        prev_hash = django_data.get("_hash", None)
        current_hash = self._get_cache_file_hash(django_data)
        if prev_hash == current_hash:
            logger.info(f"Loaded collected data from cachefile: {cache_path}")
            return django_data
        else:
            logger.debug(f"Cachefile hash does not match {current_hash} != {prev_hash}")

    def _store_django_data_to_cache(self, django_data):
        django_data["_hash"] = self._get_cache_file_hash(django_data)

        cache_path = self._get_cache_location()
        try:
            with open(cache_path, "w") as f:
                json.dump(django_data, f)
                logger.info(f"Wrote collected data to cachefile: {cache_path}")
        except Exception:
            logger.warning(f"Cannot write cachefile: {cache_path}", exc_info=True)

    def _get_cache_file_hash(self, django_data):
        start_time = time.time()

        patterns = []
        if self.project_env_path and self.project_env_path.startswith(
            self.project_src_path
        ):
            # Prevent using env directory because this increase the calculation
            # time by 100x
            for file_ in os.scandir(self.project_src_path):
                if file_.is_dir():
                    full_path = os.path.join(self.project_src_path, file_)
                    for pattern in django_data.get("file_watcher_globs", []):
                        if not full_path.startswith(self.project_env_path):
                            patterns.append(os.path.join(full_path, pattern))
        else:
            patterns = list(
                [
                    os.path.join(self.project_src_path, pattern)
                    for pattern in django_data.get("file_watcher_globs", [])
                ]
            )

        files = set(
            file_
            for pattern in patterns
            for file_ in glob.iglob(pattern, recursive=True)
        )
        files.add(DJANGO_COLLECTOR_SCRIPT_PATH)

        files_hash = hashlib.blake2b(digest_size=16)
        for file_path in sorted(files):
            if "__pycache__" not in file_path and os.path.isfile(file_path):
                files_hash.update(f"{os.stat(file_path).st_mtime}".encode())

        logger.debug(f"Caculating cache hash took {time.time() - start_time:.4f}s")

        return files_hash.hexdigest()

    def _get_cache_location(self):
        if self.cache is True and self.workspace.root_path:
            prefix = hashlib.md5(self.workspace.root_path.encode("utf-8")).hexdigest()
            return os.path.join(tempfile.gettempdir(), f"djlsp-data-{prefix}.json")
        return self.cache

    def _get_django_data_from_python_path(self, python_path):
        logger.info(f"Collection django data from local python path: {python_path}")

        command = list(
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
                    f"--project-src={self.project_src_path}",
                ],
            )
        )

        logger.debug(f"Collector command: {' '.join(command)}")

        try:
            return json.loads(subprocess.check_output(command).decode())
        except Exception:
            logger.error("Collector failed with:", exc_info=True)
            return False

    def _has_valid_docker_service(self):
        if os.path.exists(self.docker_compose_path):
            services = (
                subprocess.check_output(
                    [
                        "docker",
                        "compose",
                        f"--file={self.docker_compose_path}",
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

        docker_image = self._get_docker_image()
        if not docker_image:
            return False

        docker_run_command = list(
            filter(
                None,
                [
                    "docker",
                    "run",
                    "--rm",
                    f"--volume={DJANGO_COLLECTOR_SCRIPT_PATH}:/django-collector.py",
                    f"--volume={self.project_src_path}:/src",
                    docker_image,
                    "python",
                    "/django-collector.py",
                    (
                        f"--django-settings-module={self.django_settings_module}"
                        if self.django_settings_module
                        else None
                    ),
                    "--project-src=/src",
                ],
            )
        )

        logger.debug(f"Collector command: {' '.join(docker_run_command)}")

        try:
            return json.loads(subprocess.check_output(docker_run_command).decode())
        except Exception as e:
            logger.error(e)
            return False

    def _get_docker_image(self):
        try:
            # Make sure image is created
            subprocess.check_call(
                [
                    "docker",
                    "compose",
                    f"--file={self.docker_compose_path}",
                    "create",
                    "--no-recreate",
                    self.docker_compose_service,
                ]
            )
        except Exception as e:
            logger.error(e)
            return None

        try:
            images = json.loads(
                subprocess.check_output(
                    [
                        "docker",
                        "compose",
                        f"--file={self.docker_compose_path}",
                        "images",
                        self.docker_compose_service,
                        "--format=json",
                    ]
                )
            )
        except Exception as e:
            logger.error(e)
            return None

        if images:
            return images[0]["ID"]
        return None


server = DjangoTemplateLanguageServer("django-template-lsp", __version__)


@server.feature(INITIALIZE)
def initialized(ls: DjangoTemplateLanguageServer, params: InitializeParams):
    logger.info(f"COMMAND: {INITIALIZE}")
    logger.debug(f"OPTIONS: {params.initialization_options}")
    if params.initialization_options:
        ls.set_initialization_options(params.initialization_options)
    ls.check_version()
    ls.get_django_data()
    ls.is_initialized = True


@server.feature(
    TEXT_DOCUMENT_COMPLETION,
    CompletionOptions(trigger_characters=[" ", "|", "'", '"', "."], resolve_provider=True),
)
def completions(ls: DjangoTemplateLanguageServer, params: CompletionParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_COMPLETION}")
    logger.debug(f"PARAMS: {params}")
    try:
        return CompletionList(
            is_incomplete=False,
            items=TemplateParser(
                workspace_index=ls.workspace_index,
                jedi_project=ls.jedi_project,
                document=server.workspace.get_document(params.text_document.uri),
            ).completions(params.position.line, params.position.character),
        )
    except Exception as e:
        logger.error(e)
        return None


@server.feature(COMPLETION_ITEM_RESOLVE)
def completion_item_resolve(ls: DjangoTemplateLanguageServer, item: CompletionItem):
    logger.info(f"COMMAND: {COMPLETION_ITEM_RESOLVE}")
    logger.debug(f"PARAMS: {item}")

    if not item.documentation:
        completion = _MOST_RECENT_COMPLETIONS[item.label]
        item.detail = f"{completion.name}: {completion.type}"
        item.documentation = completion.docstring()

    return item


@server.feature(TEXT_DOCUMENT_HOVER)
def hover(ls: DjangoTemplateLanguageServer, params: HoverParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_HOVER}")
    logger.debug(f"PARAMS: {params}")
    try:
        return TemplateParser(
            workspace_index=ls.workspace_index,
            jedi_project=ls.jedi_project,
            document=server.workspace.get_document(params.text_document.uri),
        ).hover(params.position.line, params.position.character)
    except Exception as e:
        logger.error(e)
        return None


@server.feature(TEXT_DOCUMENT_DEFINITION)
def goto_definition(ls: DjangoTemplateLanguageServer, params: DefinitionParams):
    logger.info(f"COMMAND: {TEXT_DOCUMENT_DEFINITION}")
    logger.debug(f"PARAMS: {params}")
    try:
        return TemplateParser(
            workspace_index=ls.workspace_index,
            jedi_project=ls.jedi_project,
            document=ls.workspace.get_document(params.text_document.uri),
        ).goto_definition(params.position.line, params.position.character)
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
    # TODO: Do partial collect based on changed file type
    ls.get_django_data()
