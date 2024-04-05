"""Manage people in GitHub Organization"""

import logging
from dataclasses import dataclass, field

from github import Github, NamedUser, Organization, Team

from . import configure_logger
from .config import get_config
from .ghapi import get_github_token

ORG = "OpenRailAssociation"


@dataclass
class GHorg:  # pylint: disable=too-many-instance-attributes
    """Dataclass holding GH organization data and functions"""

    gh: Github = None
    org: Organization.Organization = None
    current_members: list[NamedUser.NamedUser] = field(default_factory=list)
    configured_members: dict[str, dict] = field(default_factory=dict)
    missing_members_at_github: dict[str, dict] = field(default_factory=dict)
    unconfigured_members: list[str] = field(default_factory=list)
    current_teams: list[Team.Team] = field(default_factory=list)
    configured_teams: dict[str, dict | None] = field(default_factory=dict)

    # --------------------------------------------------------------------------
    # Helper functions
    # --------------------------------------------------------------------------
    def _sluggify_teamname(self, team: str) -> str:
        """Slugify a GitHub team name"""
        # TODO: this is very naive, no other special chars are
        # supported, or multiple spaces etc.
        return team.replace(" ", "-")

    def login(self, orgname):
        """Login to GH, gather org data"""
        self.gh = Github(get_github_token())
        self.org = self.gh.get_organization(orgname)

    # --------------------------------------------------------------------------
    # Teams
    # --------------------------------------------------------------------------
    def get_current_teams(self):
        """Get teams of the existing organisation"""

        self.current_teams = list(self.org.get_teams())

    def read_configured_teams(self):
        """Import configured teams of the org"""

        # TODO: Figure out whether all config shall be in one file, and which one
        self.configured_teams = get_config("config/openrailassociation.yaml", "teams")

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
                    parent_id = self.org.get_team_by_slug(self._sluggify_teamname(parent)).id

                    logging.info("Creating team '%s' with parent ID '%s'", team, parent_id)
                    self.org.create_team(team, parent_team_id=parent_id)

                else:
                    logging.info("Creating team '%s' without parent", team)
                    self.org.create_team(team, privacy="closed")

            else:
                logging.debug("Team '%s' already exists", team)

        # Re-scan current teams as new ones may have been created
        self.get_current_teams()

    # --------------------------------------------------------------------------
    # Members
    # --------------------------------------------------------------------------
    def get_current_members(self):
        """Get all current members of the org, lower-cased"""
        for member in self.org.get_members():
            self.current_members.append(member)

    def sync_teams_members(self):
        """Check the configured members of each team, add missing ones and delete unconfigured"""
        # TODO: Make a Team sub-dataclass of this
        for team in self.current_teams:
            print()
            print(team)

            # Handle the team not being configured locally
            if team.name not in self.configured_teams:
                logging.warning("Team '%s' does not seem to be configured locally", team.name)
                continue

            # Get locally configured team members
            local_team = self.configured_teams.get(team.name)

            if not isinstance(local_team, dict) or not local_team.get('members'):
                logging.debug("Team '%s' has no configured members", team.name)
                configured_team_members = []
            else:
                configured_team_members = [
                    self.gh.get_user(user) for user in local_team.get("members")
                ]

            # Get actual team members at GitHub
            current_team_members = list(team.get_members())

            print(f"Current members: {current_team_members}")
            print(f"Configured members: {configured_team_members}")

            # TODO: Delete users who are in team but shouldn't
            # TODO: Add users who are not in team but should

    # def compare_memberlists(self):
    #     """Find out which members are configured but not part of the org yet"""

    #     # Get list of current and configured members
    #     self.get_current_members()
    #     self.read_configured_members()

    #     # Compare both lists in both ways
    #     for member, config in self.configured_members.items():
    #         if member not in self.current_members:
    #             self.missing_members_at_github[member] = config
    #     for member in self.current_members:
    #         if member not in self.configured_members:
    #             self.unconfigured_members.append(member)

    # def invite_missing_members(self):
    #     """Invite the missing members to the org and the configured teams"""

    #     # Compare the memberlists
    #     self.compare_memberlists()

    #     for username, config in self.missing_members_at_github.items():
    #         # Get team object for each desired team name
    #         userobj = self.gh.get_user(username)
    #         teamobjs = []
    #         for team in filter(None, config.get("teams")):
    #             teamobjs.append(self.org.get_team_by_slug(self._sluggify_teamname(team)))

    #         logging.info(
    #             "Inviting user '%s' to the following teams: %s",
    #             username,
    #             ", ".join(filter(None, config.get("teams"))),
    #         )
    #         self.org.invite_user(userobj, teams=teamobjs)


def main():
    """Main function"""
    configure_logger()
    org = GHorg()
    org.login(ORG)
    org.create_missing_teams()
    org.sync_teams_members()

    print(org)
