"""Class for the GitHub organization which contains most of the logic"""

import logging
from dataclasses import asdict, dataclass, field

from github import (
    Github,
    NamedUser,
    Organization,
    Repository,
    Team,
    UnknownObjectException,
)

from ._gh_api import get_github_token


@dataclass
class GHorg:  # pylint: disable=too-many-instance-attributes
    """Dataclass holding GH organization data and functions"""

    gh: Github = None  # type: ignore
    org: Organization.Organization = None  # type: ignore
    org_owners: list[NamedUser.NamedUser] = field(default_factory=list)
    org_members: list[NamedUser.NamedUser] = field(default_factory=list)
    current_teams: dict[Team.Team, dict] = field(default_factory=dict)
    configured_teams: dict[str, dict | None] = field(default_factory=dict)
    current_repos: dict[Repository.Repository, dict[Team.Team, str]] = field(default_factory=dict)

    # --------------------------------------------------------------------------
    # Helper functions
    # --------------------------------------------------------------------------
    def _sluggify_teamname(self, team: str) -> str:
        """Slugify a GitHub team name"""
        # TODO: this is very naive, no other special chars are
        # supported, or multiple spaces etc.
        return team.replace(" ", "-")

    def login(self, orgname: str, token: str):
        """Login to GH, gather org data"""
        self.gh = Github(get_github_token(token))
        self.org = self.gh.get_organization(orgname)

    def ratelimit(self):
        """Get current rate limit"""
        core = self.gh.get_rate_limit().core
        logging.debug(
            "Current rate limit: %s/%s (reset: %s)", core.remaining, core.limit, core.reset
        )

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

    def create_missing_teams(self, dry: bool = False):
        """Find out which teams are configured but not part of the org yet"""

        # Get list of current teams
        self.get_current_teams()

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
    def _get_org_members(self):
        """Get all owners of the org"""
        for member in self.org.get_members(role="admin"):
            self.org_owners.append(member)
        for member in self.org.get_members(role="member"):
            self.org_members.append(member)

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

    def _resolve_gh_username(self, username: str, teamname: str) -> NamedUser.NamedUser | None:
        """Turn a username into a proper GitHub user object"""
        try:
            gh_user: NamedUser.NamedUser = self.gh.get_user(username)  # type: ignore
        except UnknownObjectException:
            logging.error(
                "The user '%s' configured as member of team '%s' does not "
                "exist on GitHub. Spelling error or did they rename themselves?",
                username,
                teamname,
            )
            return None

        return gh_user

    def sync_teams_members(self, dry: bool = False) -> None:  # pylint: disable=too-many-branches
        """Check the configured members of each team, add missing ones and delete unconfigured"""
        logging.debug("Starting to sync team members")

        # Gather all members and owners of the organisation
        self._get_org_members()

        # Get open invitations
        open_invitations = [user.login for user in self.org.invitations()]

        for team, team_attrs in self.current_teams.items():
            # Update current team members with dict[NamedUser, str (role)]
            team_attrs["members"] = self._get_current_team_members(team)

            # For the rest of the function however, we use just the login name
            # for each current user
            current_team_members = {
                user.login: role for user, role in team_attrs["members"].items()
            }

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
            configured_users: dict[str, str] = {}
            for config_role in ("member", "maintainer"):
                team_members = self._get_configured_team_members(
                    team_configuration, team.name, config_role
                )
                for team_member in team_members:
                    # Add user with role to dict
                    configured_users.update({team_member: config_role})

            # Consider all GitHub organisation team maintainers if they are member of the team
            # This is because GitHub API returns them as maintainers even if they are just members
            for user in self.org_owners:
                if user.login in configured_users:
                    logging.debug(
                        "Overriding role of organisation owner '%s' to maintainer", user.login
                    )
                    configured_users[user.login] = "maintainer"

            # Only make edits to the team membership if the current state differs from config
            if configured_users == current_team_members:
                logging.info("Team '%s' configuration is in sync, no changes", team.name)
                continue

            # Loop through the configured users, add / update them if necessary
            for config_user, config_role in configured_users.items():
                # Add user if they haven't been in the team yet
                if config_user not in current_team_members:
                    # Turn user to GitHub object, trying to find them
                    if not (gh_user := self._resolve_gh_username(config_user, team.name)):
                        continue

                    # Do not reinvite user if their invitation is already pending
                    if config_user in open_invitations:
                        logging.info(
                            "User '%s' shall be added to team '%s' as %s, invitation is pending",
                            gh_user.login,
                            team.name,
                            config_role,
                        )
                        continue

                    logging.info(
                        "Adding user '%s' to team '%s' as %s",
                        gh_user.login,
                        team.name,
                        config_role,
                    )
                    if not dry:
                        team.add_membership(member=gh_user, role=config_role)

                # Update roles if they differ from old role
                elif config_role != current_team_members.get(config_user, ""):
                    # Turn user to GitHub object, trying to find them
                    if not (gh_user := self._resolve_gh_username(config_user, team.name)):
                        continue
                    logging.info(
                        "Updating role of '%s' in team '%s' to %s",
                        config_user,
                        team.name,
                        config_role,
                    )
                    if not dry:
                        team.add_membership(member=gh_user, role=config_role)

            # Loop through all current members. Remove them if they are not configured
            for current_user in current_team_members:
                if current_user not in configured_users:
                    # Turn user to GitHub object, trying to find them
                    if not (gh_user := self._resolve_gh_username(current_user, team.name)):
                        continue
                    if team.has_in_members(gh_user):
                        logging.info(
                            "Removing '%s' from team '%s' as they are not configured",
                            gh_user.login,
                            team.name,
                        )
                        if not dry:
                            team.remove_membership(gh_user)
                    else:
                        logging.debug(
                            "User '%s' does not need to be removed from team '%s' "
                            "as they are just member of a child-team",
                            gh_user.login,
                            team.name,
                        )

    def get_members_without_team(self) -> None:
        """Get all organisation members without any team membership"""
        # Combine org owners and org members
        all_org_members = set(self.org_members + self.org_owners)

        # Get all members of all teams
        all_team_members_lst = []
        for _, team_attrs in self.current_teams.items():
            for member in team_attrs.get("members", {}):
                all_team_members_lst.append(member)
        all_team_members = set(all_team_members_lst)

        # Find members that are in org_members but not team_members
        members_without_team = all_org_members.difference(all_team_members)

        if members_without_team:
            members_without_team_str = [user.login for user in members_without_team]
            logging.warning(
                "The following members of your GitHub organisation are not member of any team: %s",
                ", ".join(members_without_team_str),
            )

    # --------------------------------------------------------------------------
    # Repos
    # --------------------------------------------------------------------------
    def _get_current_repos_and_perms(self) -> None:
        """Get all repos, their current teams and their permissions"""
        for repo in list(self.org.get_repos()):
            self.current_repos[repo] = {}
            for team in list(repo.get_teams()):
                self.current_repos[repo][team] = team.permission

    def _create_perms_changelist_for_teams(
        self,
    ) -> dict[Team.Team, dict[Repository.Repository, str]]:
        """Create a permission/repo changelist from the perspective of configured teams"""
        team_changelist: dict[Team.Team, dict[Repository.Repository, str]] = {}
        for team_name, team_attrs in self.configured_teams.items():
            # Handle unset configured attributes
            if team_attrs is None:
                continue

            # Convert team name to Team object
            team = self.org.get_team_by_slug(self._sluggify_teamname(team_name))

            # Get configured repo permissions
            for repo, perm in team_attrs.get("repos", {}).items():
                # Convert repo to Repo object
                try:
                    repo = self.org.get_repo(repo)
                except UnknownObjectException:
                    logging.warning(
                        "Configured repository '%s' for team '%s' has not been "
                        "found in the organisation",
                        repo,
                        team.name,
                    )
                    continue

                if perm != self.current_repos[repo].get(team):
                    # Add the changeset to the changelist
                    if team not in team_changelist:
                        team_changelist[team] = {}
                    team_changelist[team][repo] = perm

        return team_changelist

    def sync_repo_permissions(self, dry: bool = False) -> None:
        """Synchronise the repository permissions of all teams"""
        logging.debug("Starting to sync repo/team permissions")

        # Get all repos and their current permissions from GitHub
        self._get_current_repos_and_perms()

        # Find differences between configured permissions for a team's repo and the current state
        for team, repos in self._create_perms_changelist_for_teams().items():
            for repo, perm in repos.items():
                logging.info(
                    "Changing permission of repository '%s' for team '%s' to '%s'",
                    repo.name,
                    team.name,
                    perm,
                )
                if not dry:
                    # Update permissions or newly add a team to a repo
                    team.update_team_repository(repo, perm)

        # Find out whether repos' permissions contain *configured* teams that
        # should not have permissions
        for repo, teams in self.current_repos.items():
            for team in teams:
                # Get configured repos for this team, finding out whether repo
                # is configured for this team
                remove = False
                # Handle: Team is not configured at all
                if team.name not in self.configured_teams:
                    logging.warning(
                        "Team '%s' has permissions on repository '%s', but this team "
                        "is not configured locally",
                        team.name,
                        repo.name,
                    )
                    continue
                # Handle: Team is configured, but contains no config
                if self.configured_teams[team.name] is None:
                    remove = True
                # Handle: Team is configured, contains config
                elif repos := self.configured_teams[team.name].get("repos", []):  # type: ignore
                    # If this repo has not been found in the configured repos
                    # for the team, remove all permissions
                    if repo.name not in repos:
                        remove = True
                # Handle: Team is configured, contains config, but no "repos" key
                else:
                    remove = True

                # Remove if any mismatch has been found
                if remove:
                    logging.info("Removing team '%s' from repository '%s'", team.name, repo.name)
                    if not dry:
                        team.remove_from_repos(repo)
