# SPDX-FileCopyrightText: 2024 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Manage a GitHub Organization, its teams, repository permissions, and more"""

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
parser.add_argument(
    "-A",
    "--ignore-archived",
    action="store_true",
    help="Do not take any action in ignored repositories",
)
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

    # Login to GitHub with token, get GitHub organisation
    org.login(cfg_org.get("org_name", ""), cfg_app.get("github_token", ""))
    # Get current rate limit
    org.ratelimit()

    # Create teams that aren't present at Github yet
    org.create_missing_teams(dry=args.dry)
    # Synchronise the team memberships
    org.sync_teams_members(dry=args.dry)
    # Report about organisation members that do not belong to any team
    org.get_members_without_team()
    # Synchronise the permissions of teams for all repositories
    org.sync_repo_permissions(dry=args.dry, ignore_archived=args.ignore_archived)
    # Remove individual collaborator permissions if they are higher than the one
    # from team membership (or if they are in no configured team at all)
    org.sync_repo_collaborator_permissions(dry=args.dry)

    # Debug output
    logging.debug("Final dataclass:\n%s", org.df2json())
    org.ratelimit()
