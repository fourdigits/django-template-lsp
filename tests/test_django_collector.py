import json
import os
import shutil
import subprocess

from djlsp.index import WorkspaceIndex
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

    index = WorkspaceIndex()
    index.update(django_data)

    assert "django_app_tag" in index.libraries["django_app"].tags
    assert index.libraries["django_app"].tags["django_app_tag"].docs == "Docs for tag"

    assert "django_app_filter" in index.libraries["django_app"].filters
    assert (
        index.libraries["django_app"].filters["django_app_filter"].docs
        == "Docs for filter"
    )

    assert "django_app.html" in index.templates
    assert "django_app.js" in index.static_files
    assert "django_app:index" in index.urls
    assert set(index.file_watcher_globs) == {
        "**/templates/**",
        "**/templatetags/**",
        "**/static/**",
        "**/test-templates-folder/**",
        "**/test-static-folder/**",
    }
