"""Manage people in GitHub Organization"""

import logging

from . import configure_logger
from ._gh_org import GHorg

ORG = "OpenRailAssociation"


def main():
    """Main function"""
    configure_logger()
    org = GHorg()
    org.login(ORG)
    org.create_missing_teams()
    org.sync_teams_members()

    logging.debug("Final dataclass: %s", org)
