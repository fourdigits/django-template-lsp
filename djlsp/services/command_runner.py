import logging
import subprocess
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    timed_out: bool = False
    duration: float = 0.0
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.timed_out and self.returncode == 0 and not self.error


class SubprocessRunner:
    def __init__(self, *, default_timeout: float | None = 30):
        self.default_timeout = default_timeout

    def run(
        self,
        command: list[str],
        *,
        timeout: float | None = None,
        cwd: str | None = None,
    ) -> CommandResult:
        effective_timeout = self.default_timeout if timeout is None else timeout
        start_time = time.time()
        logger.debug("Running command: %s", " ".join(command))

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=effective_timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            result = CommandResult(
                command=command,
                returncode=None,
                stdout=self._decode_output(exc.stdout),
                stderr=self._decode_output(exc.stderr),
                timed_out=True,
                duration=time.time() - start_time,
                error=f"Command timed out after {effective_timeout}s",
            )
            self._log_result(result)
            return result
        except OSError as exc:
            result = CommandResult(
                command=command,
                returncode=None,
                duration=time.time() - start_time,
                error=str(exc),
            )
            self._log_result(result)
            return result

        result = CommandResult(
            command=command,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration=time.time() - start_time,
            error=(
                ""
                if completed.returncode == 0
                else f"Command exited with status {completed.returncode}"
            ),
        )
        self._log_result(result)
        return result

    def _log_result(self, result: CommandResult) -> None:
        if result.ok:
            logger.debug(
                "Command completed in %.3fs: %s",
                result.duration,
                " ".join(result.command),
            )
            return

        logger.error(
            "Command failed in %.3fs: %s",
            result.duration,
            " ".join(result.command),
        )
        if result.error:
            logger.error("Command error: %s", result.error)
        if result.stderr:
            logger.error("Command stderr: %s", result.stderr.strip())

    @staticmethod
    def _decode_output(output: bytes | str | None) -> str:
        if output is None:
            return ""
        if isinstance(output, bytes):
            return output.decode(errors="replace")
        return output
