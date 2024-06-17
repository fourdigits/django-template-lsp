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

    args = parser.parse_args()

    if args.enable_log:
        logger = logging.getLogger("djlsp")
        logger.setLevel(logging.DEBUG)
        file_handler = logging.FileHandler("djlsp.log")
        file_handler.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)

    server.start_io()
