# SPDX-FileCopyrightText: 2024 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Manage a GitHub Organization, its teams, repository permissions, and more"""

import argparse
import logging
import sys

from . import __version__
from ._config import parse_config_files
from ._gh_org import GHorg
from ._helpers import configure_logger, log_progress
from ._setup_team import setup_team

# Main parser with root-level flags
parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter
)
parser.add_argument(
    "--version", action="version", version="GitHub Organization Manager " + __version__
)

# Initiate first-level subcommands
subparsers = parser.add_subparsers(dest="command", help="Available commands", required=True)

# Common flags, usable for all effective subcommands
common_flags = argparse.ArgumentParser(add_help=False)  # No automatic help to avoid duplication
common_flags.add_argument("-v", "--verbose", action="store_true", help="Get INFO logging output")
common_flags.add_argument("-vv", "--debug", action="store_true", help="Get DEBUG logging output")

# Sync commands
parser_sync = subparsers.add_parser(
    "sync",
    help="Synchronise GitHub organization settings and teams",
    parents=[common_flags],
)
parser_sync.add_argument(
    "-c",
    "--config",
    required=True,
    help="Path to the directory in which the configuration of an GitHub organisation is located",
)
parser_sync.add_argument(
    "-o",
    "--output",
    help="Output format for report",
    choices=["json", "text"],
    default="text",
)
parser_sync.add_argument("--dry", action="store_true", help="Do not make any changes at GitHub")
parser_sync.add_argument(
    "-A",
    "--ignore-archived",
    action="store_true",
    help="Do not take any action in ignored repositories",
)
parser_sync.add_argument(
    "-f",
    "--force",
    action="store_true",
    help="Execute potentially dangerous actions which you will be warned about without this flag",
)

# Setup Team
parser_create_team = subparsers.add_parser(
    "setup-team",
    help="Helps with setting up a new team using a base template",
    parents=[common_flags],
)
parser_create_team.add_argument(
    "-n",
    "--name",
    required=True,
    help="Name of the team that shall be created",
)
parser_create_team_file = parser_create_team.add_mutually_exclusive_group(required=True)
parser_create_team_file.add_argument(
    "-c",
    "--config",
    help=(
        "Path to the directory in which the configuration of an GitHub organisation is located. "
        "If this option is used, the tool will automatically come up with a file name"
    ),
)
parser_create_team_file.add_argument(
    "-f",
    "--file",
    help="Path to the file in which the team shall be added",
)


def main():
    """Main function"""

    # Process arguments
    args = parser.parse_args()

    configure_logger(verbose=args.verbose, debug=args.debug)

    # Sync command
    if args.command == "sync":
        log_progress("Preparing...")
        if args.dry:
            logging.info("Dry-run mode activated, will not make any changes at GitHub")
        if args.force:
            logging.warning("Force mode activated, will make potentially dangerous actions")

        org = GHorg()

        # Parse configuration folder, and do sanity check
        cfg_org, cfg_app, org.configured_teams = parse_config_files(args.config)
        if not cfg_org.get("org_name"):
            logging.critical(
                "No GitHub organisation name configured in organisation settings. Cannot continue"
            )
            sys.exit(1)
        org.configured_org_owners = cfg_org.get("org_owners", [])
        org.consolidate_team_config(
            default_team_configs=cfg_org.get("defaults", {}).get("team", {})
        )

        # Login to GitHub with token, get GitHub organisation
        org.login(
            orgname=cfg_org.get("org_name", ""),
            token=cfg_app.get("github_token", ""),
            app_id=cfg_app.get("github_app_id", ""),
            app_private_key=cfg_app.get("github_app_private_key", ""),
        )
        # Get current rate limit
        org.ratelimit()

        # Synchronise organisation owners
        log_progress("Synchronising organisation owners...")
        org.sync_org_owners(dry=args.dry, force=args.force)
        # Create teams that aren't present at Github yet
        log_progress("Creating missing teams...")
        org.create_missing_teams(dry=args.dry)
        # Configure general settings of teams
        log_progress("Configuring team settings...")
        org.sync_current_teams_settings(dry=args.dry)
        # Synchronise the team memberships
        log_progress("Synchronising team memberships...")
        org.sync_teams_members(dry=args.dry)
        # Report and act on teams that are not configured locally
        log_progress("Checking for unconfigured teams...")
        org.get_unconfigured_teams(
            dry=args.dry,
            delete_unconfigured_teams=cfg_app.get("delete_unconfigured_teams", False),
        )
        # Report and act on organisation members that do not belong to any team
        log_progress("Checking for members without team...")
        org.get_members_without_team(
            dry=args.dry,
            remove_members_without_team=cfg_app.get("remove_members_without_team", False),
        )
        # Synchronise the permissions of teams for all repositories
        log_progress("Synchronising team permissions...")
        org.sync_repo_permissions(dry=args.dry, ignore_archived=args.ignore_archived)
        # Remove individual collaborator permissions if they are higher than the one
        # from team membership (or if they are in no configured team at all)
        log_progress("Synchronising individual collaborator permissions...")
        org.sync_repo_collaborator_permissions(dry=args.dry)

        # Debug output
        log_progress("")  # clear progress
        logging.debug("Final dataclass:\n%s", org.pretty_print_dataclass())
        org.ratelimit()

        # Print changes
        org.stats.print_changes(
            orgname=cfg_org.get("org_name", ""), output=args.output, dry=args.dry
        )

    # Setup Team command
    elif args.command == "setup-team":
        setup_team(team_name=args.name, config_path=args.config, file_path=args.file)
