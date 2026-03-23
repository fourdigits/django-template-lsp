import json
import os
import sys
import time

from djlsp.services import (
    DJANGO_COLLECTOR_SCRIPT_PATH,
    CacheService,
    CollectorRequest,
    CollectorRunnerService,
    SubprocessRunner,
    VersionCheckService,
    WatcherService,
)
from tests.test_django_collector import (
    DJANGO_TEST_PROJECT_SRC,
    DJANGO_TEST_SETTINGS_MODULE,
)


def test_subprocess_runner_captures_stdout():
    result = SubprocessRunner().run([sys.executable, "-c", "print('hello')"])

    assert result.ok
    assert result.returncode == 0
    assert result.stdout.strip() == "hello"


def test_subprocess_runner_reports_timeout():
    result = SubprocessRunner().run(
        [sys.executable, "-c", "import time; time.sleep(0.2)"],
        timeout=0.01,
    )

    assert not result.ok
    assert result.timed_out is True
    assert "timed out" in result.error


def test_collector_runner_collects_sample_project_data():
    cache_service = CacheService(collector_script_path=DJANGO_COLLECTOR_SCRIPT_PATH)
    runner = CollectorRunnerService(
        command_runner=SubprocessRunner(),
        cache_service=cache_service,
        collector_script_path=DJANGO_COLLECTOR_SCRIPT_PATH,
    )
    result = runner.collect(
        CollectorRequest(
            workspace_root=DJANGO_TEST_PROJECT_SRC,
            project_src_path=DJANGO_TEST_PROJECT_SRC,
            project_env_path=sys.prefix,
            docker_compose_path=os.path.join(
                DJANGO_TEST_PROJECT_SRC, "docker-compose.yml"
            ),
            django_settings_module=DJANGO_TEST_SETTINGS_MODULE,
            cache=False,
        )
    )

    assert result.source == "environment python"
    assert result.django_data is not None
    assert "django_app" in result.django_data["libraries"]


def test_cache_service_invalidates_when_watched_files_change(tmp_path):
    src_path = tmp_path / "src"
    template_dir = src_path / "app" / "templates"
    template_dir.mkdir(parents=True)
    template_file = template_dir / "index.html"
    template_file.write_text("hello")

    cache_path = tmp_path / "cache.json"
    request = CollectorRequest(
        workspace_root=str(tmp_path),
        project_src_path=str(src_path),
        project_env_path=None,
        docker_compose_path=str(tmp_path / "docker-compose.yml"),
        cache=str(cache_path),
    )
    django_data = {"file_watcher_globs": ["**/templates/**"], "libraries": {}}
    service = CacheService(collector_script_path=DJANGO_COLLECTOR_SCRIPT_PATH)

    service.store(request, django_data)
    assert service.load(request) is not None

    next_timestamp = time.time() + 5
    os.utime(template_file, (next_timestamp, next_timestamp))
    assert service.load(request) is None


def test_watcher_service_updates_registration_once():
    service = WatcherService()

    registration = service.build_registration(["**/templates/**"])
    assert registration is not None
    assert (
        registration.registrations[0].register_options.watchers[0].glob_pattern
        == "**/templates/**"
    )
    assert service.build_registration(["**/templates/**"]) is None


def test_version_check_service_detects_upgrade():
    class FakeResponse:
        status = 200

        @staticmethod
        def read():
            return json.dumps({"info": {"version": "1.2.3"}}).encode()

    class FakeConnection:
        def __init__(self, host, timeout):
            self.host = host
            self.timeout = timeout

        def request(self, method, path, headers):
            self.method = method
            self.path = path
            self.headers = headers

        def getresponse(self):
            return FakeResponse()

    service = VersionCheckService(connection_factory=FakeConnection)

    assert service.check_for_upgrade("1.2.2") == "1.2.3"
