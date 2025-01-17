import argparse
import logging
import os

from pygls.protocol import LanguageServerProtocol
from pygls.workspace.workspace import Workspace

from djlsp import __version__
from djlsp.server import DjangoTemplateLanguageServer, server


def main():
    parser = argparse.ArgumentParser(description="Django template LSP")
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument("--enable-log", action="store_true")
    parser.add_argument(
        "--docker-compose-file",
        type=str,
        default="docker-compose.yml",
        help="Path to the docker-compose.yml file",
    )
    parser.add_argument(
        "--docker-compose-service",
        type=str,
        default="django",
        help="Docker Compose service name for Django",
    )
    parser.add_argument(
        "--django-settings-module",
        type=str,
        default="",
        help="Django settings module. If left empty, autodetection will be attempted.",
    )
    parser.add_argument(
        "--collect",
        action="store_true",
        help="Attempt to collect Django data and display logs.",
    )

    args = parser.parse_args()

    initialization_options = {
        "docker_compose_file": args.docker_compose_file,
        "docker_compose_service": args.docker_compose_service,
        "django_settings_module": args.django_settings_module,
    }

    if args.collect:
        logger = logging.getLogger("djlsp")
        logger.setLevel(logging.DEBUG)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)

        logger.info(f"Workspace path: {os.getcwd()}")

        class MockLanguageServerProtocol(LanguageServerProtocol):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self._workspace = Workspace(
                    root_uri=f"file://{os.getcwd()}",
                )

        language_server = DjangoTemplateLanguageServer(
            "django-template-lsp", __version__, protocol_cls=MockLanguageServerProtocol
        )
        language_server.set_initialization_options(initialization_options)
        language_server.get_django_data(update_file_watcher=False)
    else:
        if args.enable_log:
            logger = logging.getLogger("djlsp")
            logger.setLevel(logging.DEBUG)
            file_handler = logging.FileHandler("djlsp.log")
            file_handler.setLevel(logging.DEBUG)
            logger.addHandler(file_handler)

        server.set_initialization_options(initialization_options)
        server.start_io()
