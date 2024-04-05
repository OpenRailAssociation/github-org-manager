"""Class for the GitHub organization which contains most of the logic"""

import logging
from dataclasses import dataclass, field

from github import Github, NamedUser, Organization, Team, UnknownObjectException
from tqdm import tqdm

from ._config import get_config
from ._gh_api import get_github_token


@dataclass
class GHorg:  # pylint: disable=too-many-instance-attributes
    """Dataclass holding GH organization data and functions"""

    gh: Github = None  # type: ignore
    org: Organization.Organization = None  # type: ignore
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
                if parent := attributes.get("parent"):  # type: ignore
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
        for team in (pbar := tqdm(self.current_teams, desc="Teams synced")):
            logging.debug("Starting to handle team '%s'", team)
            pbar.set_postfix_str(f"Now: {team.name}")

            # Handle the team not being configured locally
            if team.name not in self.configured_teams:
                logging.warning(
                    "Team '%s' does not seem to be configured locally. "
                    "Taking no action about this team at all",
                    team.name,
                )
                continue

            # Get locally configured team members
            local_team = self.configured_teams.get(team.name)

            if not isinstance(local_team, dict) or not local_team.get("members"):
                logging.debug("Team '%s' has no configured members", team.name)
                configured_team_members = []
            else:
                try:
                    configured_team_members = [
                        self.gh.get_user(user) for user in local_team.get("members")  # type: ignore
                    ]
                except UnknownObjectException:
                    logging.error(
                        "At least one of the configured members of the team '%s' "
                        "does not seem to exist. Check the spelling! Skipping this team",
                        team.name,
                    )
                    continue

            # Get actual team members at GitHub. Problem: this also seems to
            # include child team members
            current_team_members = []
            for member in list(team.get_members()):
                if team.has_in_members(member):
                    current_team_members.append(member)

            # Add members who are not in GitHub team but should be
            members_to_be_added = set(configured_team_members).difference(current_team_members)
            for member in members_to_be_added:
                logging.info("Adding member '%s' to team '%s'", member.login, team.name)
                team.add_membership(member)  # type: ignore

            # Remove members from team as they are not configured locally
            members_to_be_removed = set(current_team_members).difference(configured_team_members)
            for member in members_to_be_removed:
                logging.info("Removing member '%s' from team '%s'", member.login, team.name)
                team.remove_membership(member)
