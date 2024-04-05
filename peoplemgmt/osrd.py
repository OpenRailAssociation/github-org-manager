"""Manage people in GitHub Organization"""

import logging
from dataclasses import dataclass, field

from github import Github

from . import configure_logger
from .config import get_config
from .ghapi import get_github_token

ORG = "OpenRailAssociation"


@dataclass
class GHorg:
    """Dataclass holding GH organization data and functions"""

    org = None
    current_members: list[str] = field(default_factory=list)
    configured_members: list[dict[str, dict]] = field(default_factory=list)
    missing_members_at_github: list[str] = field(default_factory=list)
    unconfigured_members: list[str] = field(default_factory=list)
    current_teams: list = field(default_factory=list)
    configured_teams: dict = field(default_factory=dict)

    def login(self, orgname):
        """Login to GH, gather org data"""
        self.org = Github(get_github_token()).get_organization(orgname)

    def get_current_members(self):
        """Get all current members of the org, lower-cased"""
        for member in self.org.get_members():
            self.current_members.append(member.login.lower())

    def read_configured_members(self):
        """Import configured members of the org, lower-cased"""
        members = get_config("config/openrailassociation.yaml", "members")

        # add members with their configuration, but lower-case the user name
        for member, config in members.items():
            self.configured_members.append({member.lower(): config})

    def compare_memberlists(self):
        """Find out which members are configured but not part of the org yet"""

        # Get list of current and configured members
        self.get_current_members()
        self.read_configured_members()

        # Compare both lists in both ways
        for member in self.configured_members:
            if member not in self.current_members:
                self.missing_members_at_github.append(member)
        for member in self.current_members:
            if member not in self.configured_members:
                self.unconfigured_members.append(member)

    def get_current_teams(self):
        """Get teams of the existing organisation"""
        # Reset team list as we call this function more than once
        self.current_teams = []

        for team in self.org.get_teams():
            self.current_teams.append(team)

    def read_configured_teams(self):
        """Import configured teams of the org"""
        teams = get_config("config/openrailassociation.yaml", "teams")

        def extract_teams_and_children(d, parent: str = ""):
            for k, v in d.items():
                self.configured_teams[k] = {"parent": parent}
                # has child teams
                if isinstance(v, dict):
                    extract_teams_and_children(v, parent=k)

        extract_teams_and_children(teams)

    def create_missing_teams(self):
        """Find out which teams are configured but not part of the org yet"""

        # Get list of current and configured teams
        self.get_current_teams()
        self.read_configured_teams()

        # Get the names of the existing teams
        existent_team_names = [team.name for team in self.current_teams]

        for team, attributes in self.configured_teams.items():
            if team not in existent_team_names:
                if parent := attributes.get("parent"):
                    # slugify the name
                    # TODO: this is very naive, no other special chars are
                    # supported, or multiple spaces etc.
                    parent: str = parent.replace(" ", "-")
                    parent_id = self.org.get_team_by_slug(parent).id

                logging.info("Creating team '%s' with parent ID '%s'", team, parent_id)
                self.org.create_team(team, parent_team_id=parent_id)

        # Re-scan current teams as new ones may have been created
        self.get_current_teams()


def main():
    """Main function"""
    configure_logger()
    org = GHorg()
    org.login(ORG)
    org.compare_memberlists()
    org.create_missing_teams()

    print(org)
