import http.client
import json
import logging

logger = logging.getLogger(__name__)


class VersionCheckService:
    def __init__(
        self,
        *,
        package_name: str = "django-template-lsp",
        timeout: float = 1,
        connection_factory=http.client.HTTPSConnection,
    ):
        self.package_name = package_name
        self.timeout = timeout
        self.connection_factory = connection_factory

    def get_latest_version(self) -> str | None:
        try:
            connection = self.connection_factory("pypi.org", timeout=self.timeout)
            connection.request(
                "GET",
                f"/pypi/{self.package_name}/json",
                headers={"User-Agent": "Python/3"},
            )
            response = connection.getresponse()
            if response.status != 200:
                return None
            return (
                json.loads(response.read().decode("utf-8"))
                .get("info", {})
                .get("version")
            )
        except Exception as exc:
            logger.error("Could not check latest version: %s", exc)
            return None

    def check_for_upgrade(self, current_version: str) -> str | None:
        latest_version = self.get_latest_version()
        if latest_version and self.parse_version(latest_version) > self.parse_version(
            current_version
        ):
            return latest_version
        return None

    @staticmethod
    def parse_version(version: str) -> tuple[int, ...]:
        return tuple(map(int, str(version).split(".")))
