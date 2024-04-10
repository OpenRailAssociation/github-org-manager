"""Manage people and teams in a GitHub Organization"""

import argparse
import logging
import sys

from . import __version__, configure_logger
from ._config import parse_config_files
from ._gh_org import GHorg

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument(
    "-c",
    "--config",
    required=True,
    help="Path to the directory in which the configuration of an GitHub organisation is located",
)
parser.add_argument("--debug", action="store_true", help="Get verbose logging output")
parser.add_argument("--dry", action="store_true", help="Do not make any changes at GitHub")
parser.add_argument("--version", action="version", version="GitHub Team Manager " + __version__)


def main():
    """Main function"""

    # Process arguments
    args = parser.parse_args()

    configure_logger(args.debug)

    if args.dry:
        logging.info("Dry-run mode activated, will not make any changes at GitHub")

    org = GHorg()

    # Parse configuration folder, and do sanity check
    cfg_org, cfg_app, org.configured_teams = parse_config_files(args.config)
    if not cfg_org.get("org_name"):
        logging.critical(
            "No GitHub organisation name configured in organisation settings. Cannot continue"
        )
        sys.exit(1)

    org.login(cfg_org.get("org_name", ""), cfg_app.get("github_token", ""))
    org.create_missing_teams(dry=args.dry)
    org.sync_teams_members(dry=args.dry)
    org.get_members_without_team()

    logging.debug("Final dataclass:\n%s", org.df2json())
