import glob
import hashlib
import json
import logging
import os
import tempfile
import time

from djlsp.services.collector_runner import CollectorRequest

logger = logging.getLogger(__name__)


class CacheService:
    def __init__(self, *, collector_script_path: str):
        self.collector_script_path = collector_script_path

    def load(self, request: CollectorRequest) -> dict | None:
        cache_path = self.get_cache_location(request)
        if not cache_path or not os.path.isfile(cache_path):
            return None

        logger.debug("Found cachefile: %s", cache_path)
        try:
            with open(cache_path, "r") as file_:
                django_data = json.load(file_)
        except Exception:
            logger.warning("Cannot read cachefile: %s", cache_path, exc_info=True)
            return None
        if not isinstance(django_data, dict):
            logger.warning("Cachefile has invalid payload type: %s", type(django_data))
            return None

        prev_hash = django_data.get("_hash")
        current_hash = self.get_cache_file_hash(request, django_data)
        if prev_hash == current_hash:
            logger.info("Loaded collected data from cachefile: %s", cache_path)
            return django_data

        logger.debug("Cachefile hash does not match %s != %s", current_hash, prev_hash)
        return None

    def store(self, request: CollectorRequest, django_data: dict) -> None:
        cache_path = self.get_cache_location(request)
        if not cache_path:
            return

        cache_data = dict(django_data)
        cache_data["_hash"] = self.get_cache_file_hash(request, cache_data)

        try:
            with open(cache_path, "w") as file_:
                json.dump(cache_data, file_)
            logger.info("Wrote collected data to cachefile: %s", cache_path)
        except Exception:
            logger.warning("Cannot write cachefile: %s", cache_path, exc_info=True)

    def get_cache_location(self, request: CollectorRequest) -> str | None:
        if request.cache is True and request.workspace_root:
            prefix = hashlib.md5(request.workspace_root.encode("utf-8")).hexdigest()
            return os.path.join(tempfile.gettempdir(), f"djlsp-data-{prefix}.json")

        if isinstance(request.cache, str):
            return request.cache

        return None

    def get_cache_file_hash(self, request: CollectorRequest, django_data: dict) -> str:
        start_time = time.time()
        patterns = self._get_hash_patterns(request, django_data)

        files = {
            file_
            for pattern in patterns
            for file_ in glob.iglob(pattern, recursive=True)
        }
        files.add(self.collector_script_path)

        files_hash = hashlib.blake2b(digest_size=16)
        for file_path in sorted(files):
            if "__pycache__" not in file_path and os.path.isfile(file_path):
                files_hash.update(f"{os.stat(file_path).st_mtime}".encode())

        logger.debug("Calculating cache hash took %.4fs", time.time() - start_time)
        return files_hash.hexdigest()

    def _get_hash_patterns(
        self, request: CollectorRequest, django_data: dict
    ) -> list[str]:
        file_watcher_globs = django_data.get("file_watcher_globs", [])

        if (
            request.project_env_path
            and request.project_src_path
            and request.project_env_path.startswith(request.project_src_path)
        ):
            patterns = []
            for file_ in os.scandir(request.project_src_path):
                if not file_.is_dir() or file_.path.startswith(
                    request.project_env_path
                ):
                    continue
                for pattern in file_watcher_globs:
                    patterns.append(os.path.join(file_.path, pattern))
            return patterns

        return [
            os.path.join(request.project_src_path, pattern)
            for pattern in file_watcher_globs
        ]
