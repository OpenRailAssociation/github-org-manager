"""Class for the GitHub organization which contains most of the logic"""

import logging
from dataclasses import asdict, dataclass, field

from github import Github, NamedUser, Organization, Team, UnknownObjectException

from ._config import get_config
from ._gh_api import get_github_token


@dataclass
class GHorg:  # pylint: disable=too-many-instance-attributes
    """Dataclass holding GH organization data and functions"""

    gh: Github = None  # type: ignore
    org: Organization.Organization = None  # type: ignore
    org_owners: list[NamedUser.NamedUser] = field(default_factory=list)
    # {Team: {"members": dict[NamedUsers], "repos": dict[Repo]}}
    current_teams: dict[Team.Team, dict] = field(default_factory=dict)
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

    def df2json(self) -> str:
        """Convert the dataclass to a JSON string"""
        d = asdict(self)

        def pretty(d, indent=0):
            string = ""
            for key, value in d.items():
                string += "  " * indent + str(key) + ":\n"
                if isinstance(value, dict):
                    string += pretty(value, indent + 1)
                else:
                    string += "  " * (indent + 1) + str(value) + "\n"

            return string

        return pretty(d)

    # --------------------------------------------------------------------------
    # Teams
    # --------------------------------------------------------------------------
    def get_current_teams(self):
        """Get teams of the existing organisation"""

        for team in list(self.org.get_teams()):
            self.current_teams[team] = {"members": {}, "repos": {}}

    def read_configured_teams(self):
        """Import configured teams of the org"""

        # TODO: Figure out whether all config shall be in one file, and which one
        self.configured_teams = get_config("config/openrailassociation.yaml", "teams")

    def create_missing_teams(self, dry: bool = False):
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
                    if not dry:
                        self.org.create_team(team, parent_team_id=parent_id)

                else:
                    logging.info("Creating team '%s' without parent", team)
                    if not dry:
                        self.org.create_team(team, privacy="closed")

            else:
                logging.debug("Team '%s' already exists", team)

        # Re-scan current teams as new ones may have been created
        self.get_current_teams()

    # --------------------------------------------------------------------------
    # Members
    # --------------------------------------------------------------------------
    def _get_org_owners(self):
        """Get all owners of the org"""
        for member in self.org.get_members(role="admin"):
            self.org_owners.append(member)

    def _get_configured_team_members(
        self, team_config: dict, team_name: str, role: str
    ) -> list[str]:
        """Read configured members/maintainers from the configuration"""

        if isinstance(team_config, dict) and team_config.get(role):
            configured_team_members = []
            for user in team_config.get(role, []):
                configured_team_members.append(user)

            return configured_team_members

        logging.debug("Team '%s' has no configured %ss", team_name, role)
        return []

    def _get_current_team_members(self, team: Team.Team) -> dict[NamedUser.NamedUser, str]:
        """Return dict of current users with their respective roles. Also
        contains members of child teams"""
        current_users: dict[NamedUser.NamedUser, str] = {}
        for role in ("member", "maintainer"):
            # Make a two-step check whether person is actually in team, as
            # get_members() also return child-team members
            for user in list(team.get_members(role=role)):
                current_users.update({user: role})

        return current_users

    def sync_teams_members(self, dry: bool = False) -> None:  # pylint: disable=too-many-branches
        """Check the configured members of each team, add missing ones and delete unconfigured"""
        self._get_org_owners()

        for team, team_attrs in self.current_teams.items():
            team_attrs["members"] = self._get_current_team_members(team)

            # Handle the team not being configured locally
            if team.name not in self.configured_teams:
                logging.warning(
                    "Team '%s' does not seem to be configured locally. "
                    "Taking no action about this team at all",
                    team.name,
                )
                continue

            # Get configuration from current team
            if team_configuration := self.configured_teams.get(team.name):
                pass
            else:
                team_configuration = {}

            # Analog to team_attrs["members"], add members and maintainers to shared
            # dict with respective role, while maintainer role dominates
            configured_users: dict[NamedUser.NamedUser, str] = {}
            for config_role in ("member", "maintainer"):
                team_members = self._get_configured_team_members(
                    team_configuration, team.name, config_role
                )
                for team_member in team_members:
                    # Add user to dict, trying to find them on GitHub
                    try:
                        gh_user_obj: NamedUser.NamedUser = self.gh.get_user(
                            team_member
                        )  # type: ignore
                        configured_users.update({gh_user_obj: config_role})
                    except UnknownObjectException:
                        logging.error(
                            "The user '%s' configured as %s for the team '%s' does not "
                            "exist on GitHub. Spelling error or did they rename themselves?",
                            team_member,
                            config_role,
                            team.name,
                        )

            # Consider all GitHub organisation team maintainers if they are member of the team
            # This is because GitHub API returns them as maintainers even if they are just members
            for user in self.org_owners:
                if user in configured_users:
                    logging.debug(
                        "Overriding role of organisation owner '%s' to maintainer", user.login
                    )
                    configured_users[user] = "maintainer"

            # Only make edits to the team membership if the current state differs from config
            if configured_users == team_attrs["members"]:
                logging.info("Team '%s' configuration is in sync, no changes", team.name)
                continue

            # Loop through the configured users, add / update them if necessary
            for config_user, config_role in configured_users.items():
                # Add user if they haven't been in the team yet
                if config_user not in team_attrs["members"]:
                    logging.info(
                        "Adding '%s' to team '%s' as %s",
                        config_user.login,
                        team.name,
                        config_role,
                    )
                    if not dry:
                        team.add_membership(member=config_user, role=config_role)

                # Update roles if they differ from old role
                elif config_role != team_attrs["members"].get(config_user, ""):
                    logging.info(
                        "Updating role of '%s' in team '%s' to %s",
                        config_user.login,
                        team.name,
                        config_role,
                    )
                    if not dry:
                        team.add_membership(member=config_user, role=config_role)

            # Loop through all current members. Remove them if they are not configured
            for current_user in team_attrs["members"]:
                if current_user not in configured_users:
                    if team.has_in_members(current_user):
                        logging.info(
                            "Removing '%s' from team '%s' as they are not configured",
                            current_user.login,
                            team.name,
                        )
                        if not dry:
                            team.remove_membership(current_user)
                    else:
                        logging.debug(
                            "User '%s' does not need to be removed from team '%s' "
                            "as they are just member of a child-team",
                            current_user.login,
                            team.name,
                        )
