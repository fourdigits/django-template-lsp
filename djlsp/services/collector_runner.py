import json
import logging
import os
import shutil
from dataclasses import dataclass

from djlsp.services.command_runner import CommandResult, SubprocessRunner

logger = logging.getLogger(__name__)

DJANGO_COLLECTOR_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "..",
    "scripts",
    "django-collector.py",
)
DJANGO_COLLECTOR_SCRIPT_PATH = os.path.realpath(DJANGO_COLLECTOR_SCRIPT_PATH)


@dataclass(frozen=True)
class CollectorRequest:
    workspace_root: str | None
    project_src_path: str
    project_env_path: str | None
    docker_compose_path: str
    django_settings_module: str = ""
    docker_compose_file: str = "docker-compose.yml"
    docker_compose_service: str = "django"
    cache: bool | str = False


@dataclass(frozen=True)
class CollectorResult:
    django_data: dict | None
    source: str | None = None


class CollectorRunnerService:
    def __init__(
        self,
        *,
        command_runner: SubprocessRunner,
        cache_service,
        collector_script_path: str = DJANGO_COLLECTOR_SCRIPT_PATH,
    ):
        self.command_runner = command_runner
        self.cache_service = cache_service
        self.collector_script_path = collector_script_path

    def collect(self, request: CollectorRequest) -> CollectorResult:
        if request.cache and (django_data := self.cache_service.load(request)):
            return CollectorResult(django_data=django_data, source="cache")

        django_data = None
        source = None

        if request.project_env_path:
            django_data = self._get_django_data_from_python_path(
                python_path=os.path.join(request.project_env_path, "bin", "python"),
                project_src_path=request.project_src_path,
                django_settings_module=request.django_settings_module,
            )
            source = "environment python"
        elif self._has_valid_docker_service(request):
            django_data = self._get_django_data_from_docker(request)
            source = "docker"
        elif python_path := shutil.which("python3"):
            django_data = self._get_django_data_from_python_path(
                python_path=python_path,
                project_src_path=request.project_src_path,
                django_settings_module=request.django_settings_module,
            )
            source = "system python"

        if django_data and request.cache:
            self.cache_service.store(request, django_data)

        return CollectorResult(django_data=django_data, source=source)

    def _get_django_data_from_python_path(
        self,
        *,
        python_path: str,
        project_src_path: str,
        django_settings_module: str,
    ) -> dict | None:
        logger.info("Collecting django data from local python path: %s", python_path)
        command = [
            python_path,
            self.collector_script_path,
            *self._collector_arguments(
                project_src_path=project_src_path,
                django_settings_module=django_settings_module,
            ),
        ]
        result = self.command_runner.run(command, timeout=60)
        return self._parse_json_result(result, context="python collector")

    def _has_valid_docker_service(self, request: CollectorRequest) -> bool:
        if not os.path.exists(request.docker_compose_path):
            return False

        command = [
            "docker",
            "compose",
            f"--file={request.docker_compose_path}",
            "config",
            "--services",
        ]
        result = self.command_runner.run(command, timeout=15)
        if not result.ok:
            return False
        return request.docker_compose_service in result.stdout.splitlines()

    def _get_django_data_from_docker(self, request: CollectorRequest) -> dict | None:
        logger.info(
            "Collecting django data from docker %s:%s",
            request.docker_compose_file,
            request.docker_compose_service,
        )

        docker_image = self._get_docker_image(request)
        if not docker_image:
            return None

        command = [
            "docker",
            "run",
            "--rm",
            f"--volume={self.collector_script_path}:/django-collector.py",
            f"--volume={request.project_src_path}:/src",
            docker_image,
            "python",
            "/django-collector.py",
            *self._collector_arguments(
                project_src_path="/src",
                django_settings_module=request.django_settings_module,
            ),
        ]
        result = self.command_runner.run(command, timeout=60)
        return self._parse_json_result(result, context="docker collector")

    def _get_docker_image(self, request: CollectorRequest) -> str | None:
        create_command = [
            "docker",
            "compose",
            f"--file={request.docker_compose_path}",
            "create",
            "--no-recreate",
            request.docker_compose_service,
        ]
        create_result = self.command_runner.run(create_command, timeout=30)
        if not create_result.ok:
            return None

        images_command = [
            "docker",
            "compose",
            f"--file={request.docker_compose_path}",
            "images",
            request.docker_compose_service,
            "--format=json",
        ]
        images_result = self.command_runner.run(images_command, timeout=15)
        images = self._parse_json_result(images_result, context="docker images")
        if images:
            return images[0]["ID"]
        return None

    def _collector_arguments(
        self,
        *,
        project_src_path: str,
        django_settings_module: str,
    ) -> list[str]:
        args = [f"--project-src={project_src_path}"]
        if django_settings_module:
            args.insert(0, f"--django-settings-module={django_settings_module}")
        return args

    def _parse_json_result(
        self,
        result: CommandResult,
        *,
        context: str,
    ) -> dict | list | None:
        if not result.ok:
            logger.error("%s failed", context)
            return None

        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            logger.error("%s returned invalid JSON", context, exc_info=True)
            return None
