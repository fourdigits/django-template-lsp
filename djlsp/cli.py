import argparse
import logging

from djlsp import __version__
from djlsp.server import server


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

    args = parser.parse_args()

    if args.enable_log:
        logger = logging.getLogger("djlsp")
        logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler("djlsp.log")
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    server.set_initialization_options(
        {
            "docker_compose_file": args.docker_compose_file,
            "docker_compose_service": args.docker_compose_service,
            "django_settings_module": args.django_settings_module,
        }
    )

    server.start_io()
