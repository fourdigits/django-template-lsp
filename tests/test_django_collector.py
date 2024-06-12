import json
import os
import shutil
import subprocess

from djlsp.server import DJANGO_COLLECTOR_SCRIPT_PATH

DJANGO_TEST_PROJECT_SRC = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "django_test",
)
DJANGO_TEST_SETTINGS_MODULE = "django_test.settings"


def test_django_collect():
    django_data = json.loads(
        subprocess.check_output(
            [
                shutil.which("python"),  # Get tox python path
                DJANGO_COLLECTOR_SCRIPT_PATH,
                f"--django-settings-module={DJANGO_TEST_SETTINGS_MODULE}",
                f"--project-src={DJANGO_TEST_PROJECT_SRC}",
            ]
        )
    )

    assert "django_app" in django_data["libraries"]
    assert "django_app_tag" in django_data["libraries"]["django_app"]["tags"]
    assert "django_app_filter" in django_data["libraries"]["django_app"]["filters"]
    assert "django_app.html" in django_data["templates"]
    assert "django_app.js" in django_data["static_files"]
    assert "django_app:index" in django_data["urls"]
    assert set(django_data["file_watcher_globs"]) == {
        "**/templates/**",
        "**/templatetags/**",
        "**/static/**",
        "**/test-templates-folder/**",
        "**/test-static-folder/**",
    }
