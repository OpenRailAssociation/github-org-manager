"""Manage people and teams in a GitHub Organization"""

import argparse
import logging

from . import __version__, configure_logger
from ._gh_org import GHorg

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument(
    "-o",
    "--organization",
    required=True,
    help="Name of the GitHub organization you would like to handle",
)
parser.add_argument("--debug", action="store_true", help="Get verbose logging output")
parser.add_argument("--version", action="version", version="GitHub Team Manager " + __version__)


def main():
    """Main function"""

    # Process arguments
    args = parser.parse_args()

    configure_logger(args.debug)
    org = GHorg()
    org.login(args.organization)
    org.create_missing_teams()
    org.sync_teams_members()

    logging.debug("Final dataclass: %s", org)
