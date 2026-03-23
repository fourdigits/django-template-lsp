import logging
import threading
import uuid
from urllib.parse import urlparse

from lsprotocol.types import (
    DidChangeWatchedFilesRegistrationOptions,
    FileSystemWatcher,
    Registration,
    RegistrationParams,
)

logger = logging.getLogger(__name__)


class WatcherService:
    def __init__(self, *, debounce_seconds: float = 0.2):
        self.file_watcher_id = str(uuid.uuid4())
        self.current_globs: list[str] = []
        self.debounce_seconds = debounce_seconds
        self._lock = threading.Lock()
        self._timer: threading.Timer | None = None
        self._pending_change_kinds: set[str] = set()

    def build_registration(self, glob_patterns: list[str]) -> RegistrationParams | None:
        if set(glob_patterns) == set(self.current_globs):
            return None

        self.current_globs = list(glob_patterns)
        logger.info("Update file watcher patterns to: %s", self.current_globs)
        return RegistrationParams(
            registrations=[
                Registration(
                    id=self.file_watcher_id,
                    method="workspace/didChangeWatchedFiles",
                    register_options=DidChangeWatchedFilesRegistrationOptions(
                        watchers=[
                            FileSystemWatcher(glob_pattern=glob_pattern)
                            for glob_pattern in self.current_globs
                        ]
                    ),
                )
            ]
        )

    def schedule_collection(self, callback, changes) -> None:
        change_kinds = self.classify_changes(changes)
        with self._lock:
            self._pending_change_kinds.update(change_kinds)
            if self._timer is not None:
                self._timer.cancel()
            self._timer = threading.Timer(
                self.debounce_seconds,
                self._flush,
                [callback],
            )
            self._timer.daemon = True
            self._timer.start()

    def classify_changes(self, changes) -> set[str]:
        kinds = set()
        for change in changes:
            path = urlparse(change.uri).path
            if "/templatetags/" in path:
                kinds.add("templatetag")
            elif "/templates/" in path:
                kinds.add("template")
            elif "/static/" in path:
                kinds.add("static")
            elif path.endswith(".py"):
                kinds.add("python")
            else:
                kinds.add("other")
        return kinds

    def collection_scope(self, change_kinds: set[str]) -> str:
        actionable_kinds = {"python", "templatetag", "template", "static"}
        if change_kinds & actionable_kinds:
            return "full"
        return "none"

    def should_collect(self, change_kinds: set[str]) -> bool:
        return self.collection_scope(change_kinds) != "none"

    def _flush(self, callback) -> None:
        with self._lock:
            change_kinds = set(self._pending_change_kinds)
            self._pending_change_kinds.clear()
            self._timer = None

        logger.debug("Debounced file watcher changes: %s", sorted(change_kinds))
        if self.should_collect(change_kinds):
            callback(change_kinds)
            return

        logger.debug(
            "Skipping collect after file watcher changes (scope=%s)",
            self.collection_scope(change_kinds),
        )
