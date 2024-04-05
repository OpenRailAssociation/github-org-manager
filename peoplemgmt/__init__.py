"""Global init file"""

import logging


def configure_logger() -> logging.Logger:
    """Set logging options"""
    log = logging.getLogger()
    logging.basicConfig(
        encoding="utf-8",
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    log.setLevel(logging.INFO)

    return log
