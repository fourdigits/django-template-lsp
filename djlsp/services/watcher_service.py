import logging
import uuid

from lsprotocol.types import (
    DidChangeWatchedFilesRegistrationOptions,
    FileSystemWatcher,
    Registration,
    RegistrationParams,
)

logger = logging.getLogger(__name__)


class WatcherService:
    def __init__(self):
        self.file_watcher_id = str(uuid.uuid4())
        self.current_globs: list[str] = []

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
