# SPDX-FileCopyrightText: 2024 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Class for the GitHub organization which contains most of the logic"""

import logging
import sys
from dataclasses import asdict, dataclass, field

from github import Github, GithubException, UnknownObjectException
from github.NamedUser import NamedUser
from github.Organization import Organization
from github.Repository import Repository
from github.Team import Team

from ._gh_api import get_github_token, run_graphql_query


@dataclass
class GHorg:  # pylint: disable=too-many-instance-attributes, too-many-lines
    """Dataclass holding GH organization data and functions"""

    gh: Github = None  # type: ignore
    org: Organization = None  # type: ignore
    gh_token: str = ""
    default_repository_permission: str = ""
    current_org_owners: list[NamedUser] = field(default_factory=list)
    configured_org_owners: list[str] = field(default_factory=list)
    org_members: list[NamedUser] = field(default_factory=list)
    current_teams: dict[Team, dict] = field(default_factory=dict)
    configured_teams: dict[str, dict | None] = field(default_factory=dict)
    newly_added_users: list[NamedUser] = field(default_factory=list)
    current_repos_teams: dict[Repository, dict[Team, str]] = field(default_factory=dict)
    current_repos_collaborators: dict[Repository, dict[str, str]] = field(default_factory=dict)
    configured_repos_collaborators: dict[str, dict[str, str]] = field(default_factory=dict)
    archived_repos: list[Repository] = field(default_factory=list)
    unconfigured_team_repo_permissions: dict[str, dict[str, str]] = field(default_factory=dict)

    # Re-usable Constants
    TEAM_CONFIG_FIELDS: dict[str, dict[str, str | None]] = field(  # pylint: disable=invalid-name
        default_factory=lambda: {
            "parent": {"fallback_value": None},
            "privacy": {"fallback_value": "<keep-current>"},
            "description": {"fallback_value": "<keep-current>"},
            "notification_setting": {"fallback_value": "<keep-current>"},
        }
    )

    # --------------------------------------------------------------------------
    # Helper functions
    # --------------------------------------------------------------------------
    def _sluggify_teamname(self, team: str) -> str:
        """Slugify a GitHub team name"""
        # TODO: this is very naive, no other special chars are
        # supported, or multiple spaces etc.
        return team.replace(" ", "-")

    def login(self, orgname: str, token: str) -> None:
        """Login to GH, gather org data"""
        self.gh_token = get_github_token(token)
        self.gh = Github(self.gh_token)
        logging.debug("Logged in as %s", self.gh.get_user().login)
        self.org = self.gh.get_organization(orgname)
        logging.debug("Gathered data from organization '%s' (%s)", self.org.login, self.org.name)

    def ratelimit(self):
        """Get current rate limit"""
        core = self.gh.get_rate_limit().core
        logging.debug(
            "Current rate limit: %s/%s (reset: %s)", core.remaining, core.limit, core.reset
        )

    def pretty_print_dict(self, dictionary: dict) -> str:
        """Convert a dict to a pretty-printed output"""

        # Censor sensible fields
        def censor_half_string(string: str) -> str:
            """Censor 50% of a string (rounded up)"""
            half1 = int(len(string) / 2)
            half2 = len(string) - half1
            return string[:half1] + "*" * (half2)

        sensible_keys = ["gh_token"]
        for key in sensible_keys:
            if value := dictionary.get(key, ""):
                dictionary[key] = censor_half_string(value)

        # Print dict nicely
        def pretty(d, indent=0):
            string = ""
            for key, value in d.items():
                string += "  " * indent + str(key) + ":\n"
                if isinstance(value, dict):
                    string += pretty(value, indent + 1)
                else:
                    string += "  " * (indent + 1) + str(value) + "\n"

            return string

        return pretty(dictionary)

    def pretty_print_dataclass(self) -> str:
        """Convert this dataclass to a pretty-printed output"""
        return self.pretty_print_dict(asdict(self))

    def compare_two_lists(self, list1: list[str], list2: list[str]):
        """
        Compares two lists of strings and returns a tuple containing elements
        missing in each list and common elements.

        Args:
            list1 (list of str): The first list of strings.
            list2 (list of str): The second list of strings.

        Returns:
            tuple: A tuple containing three lists:
                1. The first list contains elements in `list2` that are missing in `list1`.
                2. The second list contains elements that are present in both `list1` and `list2`.
                3. The third list contains elements in `list1` that are missing in `list2`.

        Example:
            >>> list1 = ["apple", "banana", "cherry"]
            >>> list2 = ["banana", "cherry", "date", "fig"]
            >>> compare_lists(list1, list2)
            (['date', 'fig'], ['banana', 'cherry'], ['apple'])
        """
        # Convert lists to sets for easier comparison
        set1, set2 = set(list1), set(list2)

        # Elements in list2 that are missing in list1
        missing_in_list1 = list(set2 - set1)

        # Elements present in both lists
        common_elements = list(set1 & set2)

        # Elements in list1 that are missing in list2
        missing_in_list2 = list(set1 - set2)

        # Return the result as a tuple
        return (missing_in_list1, common_elements, missing_in_list2)

    def compare_two_dicts(self, dict1: dict, dict2: dict) -> dict[str, dict[str, str | int | None]]:
        """Compares two dictionaries. Assume that the keys are the same. Output
        a dict with keys that have differing values"""
        # Create an empty dictionary to store differences
        differences = {}

        # Iterate through the keys (assuming both dictionaries have the same keys)
        for key in dict1:
            # Compare the values for each key
            if dict1[key] != dict2[key]:
                differences[key] = {"dict1": dict1[key], "dict2": dict2[key]}

        return differences

    def _resolve_gh_username(self, username: str, teamname: str) -> NamedUser | None:
        """Turn a username into a proper GitHub user object"""
        try:
            gh_user: NamedUser = self.gh.get_user(username)  # type: ignore
        except UnknownObjectException:
            logging.error(
                "The user '%s' configured as member of team '%s' does not "
                "exist on GitHub. Spelling error or did they rename themselves?",
                username,
                teamname,
            )
            return None

        return gh_user

    # --------------------------------------------------------------------------
    # Configuration
    # --------------------------------------------------------------------------
    def consolidate_team_config(self, default_team_configs: dict[str, str]) -> None:
        """Complete teams configuration with default teams configs"""
        for team_name, team_config in self.configured_teams.items():
            # Handle none team configs
            if team_config is None:
                team_config = {}

            # Iterate through configurable team settings. Take team config, fall
            # back to default org-wide value. If no config can be found, either
            # add a fallback value or do not add this setting altogether.
            for cfg_item, cfg_value in self.TEAM_CONFIG_FIELDS.items():
                # Case 1: setting in team config
                if tcfg := team_config.get(cfg_item):
                    team_config[cfg_item] = tcfg
                # Case 2: setting in default org team config
                elif dcfg := default_team_configs.get(cfg_item):
                    team_config[cfg_item] = dcfg
                # Case 3: setting defined nowhere, take hardcoded default
                else:
                    # Look which fallback value/action shall be taken
                    fallback_value = cfg_value["fallback_value"]
                    if fallback_value != "<keep-current>":
                        team_config[cfg_item] = fallback_value

            logging.debug("Configuration for team '%s' consolidated to: %s", team_name, team_config)

    # --------------------------------------------------------------------------
    # Owners
    # --------------------------------------------------------------------------
    def _get_current_org_owners(self) -> None:
        """Get all owners of the org"""
        # Reset the user list, then build up new list
        self.current_org_owners = []
        for member in self.org.get_members(role="admin"):
            self.current_org_owners.append(member)

    def _check_configured_org_owners(self) -> bool:
        """Check configured owners and make them lower-case for better
        comparison. Returns True if owners are well configured."""
        # Add configured owners if they are a list
        if isinstance(self.configured_org_owners, list):
            # Make all configured users lower-case
            self.configured_org_owners = [user.lower() for user in self.configured_org_owners]
        else:
            logging.warning(
                "The organisation owners are not configured as a proper list. Will not handle them."
            )
            self.configured_org_owners = []

        if not self.configured_org_owners:
            logging.warning(
                "No owners for your GitHub organisation configured. Will not make any "
                "change regarding the ownership, and continue with the current owners: %s",
                ", ".join([user.login for user in self.current_org_owners]),
            )
            return False

        return True

    def _is_user_authenticated_user(self, user: NamedUser) -> bool:
        """Check if a given NamedUser is the authenticated user"""
        if user.login == self.gh.get_user().login:
            return True
        return False

    def sync_org_owners(self, dry: bool = False, force: bool = False) -> None:
        """Synchronise the organization owners"""
        # Get current and configured owners
        self._get_current_org_owners()

        # Abort owner synchronisation if no owners are configured, or badly
        if not self._check_configured_org_owners():
            return

        # Get differences between the current and configured owners
        owners_remove, owners_ok, owners_add = self.compare_two_lists(
            self.configured_org_owners, [user.login for user in self.current_org_owners]
        )
        # Compare configured (lower-cased) owners with lower-cased list of current owners
        if not owners_remove and not owners_add:
            logging.info("Organization owners are in sync, no changes")
            return

        logging.debug(
            "Organization owners are not in sync. Config: '%s' vs. Current: '%s'",
            self.configured_org_owners,
            self.current_org_owners,
        )
        logging.debug(
            "Will remove %s, will not change %s, will add %s", owners_remove, owners_ok, owners_add
        )

        # Add the missing owners
        for user in owners_add:
            if gh_user := self._resolve_gh_username(user, "<org owners>"):
                logging.info("Adding user '%s' as organization owner", gh_user.login)
                if not dry:
                    self.org.add_to_members(gh_user, "admin")

        # Remove the surplus owners
        for user in owners_remove:
            if gh_user := self._resolve_gh_username(user, "<org owners>"):
                logging.info(
                    "User '%s' is not configured as organization owners. "
                    "Will make them a normal member",
                    gh_user.login,
                )
                # Handle authenticated user being the same as the one you want to degrade
                if self._is_user_authenticated_user(gh_user):
                    logging.warning(
                        "The user '%s' you want to remove from owners is the one you "
                        "authenticated with. This may disrupt all further operations. "
                        "Unless you run the program with --force, "
                        "this operation will not be executed.",
                        gh_user.login,
                    )
                    # Check if user forced this operation
                    if force:
                        logging.info(
                            "You called the program with --force, "
                            "so it will remove yourself from the owners"
                        )
                    else:
                        continue

                # Execute the degradation of the owner
                if not dry:
                    self.org.add_to_members(gh_user, "member")

        # Update the current organisation owners
        self._get_current_org_owners()

    # --------------------------------------------------------------------------
    # Teams
    # --------------------------------------------------------------------------
    def _get_current_teams(self):
        """Get teams of the existing organisation"""
        for team in list(self.org.get_teams()):
            self.current_teams[team] = {"members": {}, "repos": {}}

    def create_missing_teams(self, dry: bool = False):
        """Find out which teams are configured but not part of the org yet"""

        # Get list of current teams
        self._get_current_teams()

        # Get the names of the existing teams
        existent_team_names = [team.name for team in self.current_teams]

        for team, attributes in self.configured_teams.items():
            if team not in existent_team_names:
                if parent := attributes.get("parent"):  # type: ignore
                    parent_id = self.org.get_team_by_slug(self._sluggify_teamname(parent)).id

                    logging.info("Creating team '%s' with parent ID '%s'", team, parent_id)
                    # NOTE: We do not specify any team settings (description etc)
                    # here, this will happen later
                    if not dry:
                        self.org.create_team(
                            team,
                            parent_team_id=parent_id,
                            # Hardcode privacy as "secret" is not possible in child teams
                            privacy="closed",
                        )

                else:
                    logging.info("Creating team '%s' without parent", team)
                    if not dry:
                        self.org.create_team(
                            team,
                            # Hardcode privacy as "secret" is not possible in
                            # parent teams, which is the API's default
                            privacy="closed",
                        )

            else:
                logging.debug("Team '%s' already exists", team)

        # Re-scan current teams as new ones may have been created
        self._get_current_teams()

    def _prepare_team_config_for_sync(
        self, team_config: dict[str, str | int | Team | None]
    ) -> dict[str, str | int | None]:
        """Turn parent values into IDs, and sort the config dictionary for better comparison"""
        if parent := team_config["parent"]:
            # team coming from API request (current)
            if isinstance(parent, Team):
                team_config["parent_team_id"] = parent.id
            # team coming from config, and valid string
            elif isinstance(parent, str) and parent:
                team_config["parent_team_id"] = self.org.get_team_by_slug(
                    self._sluggify_teamname(parent)
                ).id
            # empty from string, so probably default value
            elif isinstance(parent, str) and not parent:
                team_config["parent_team_id"] = None
        else:
            team_config["parent_team_id"] = None

        # Remove parent key
        team_config.pop("parent", None)

        # Sort dict and return
        # Ensure the dictionary has only comparable types before sorting
        filtered_team_config = {
            k: v for k, v in team_config.items() if isinstance(v, (str, int, type(None)))
        }
        return dict(sorted(filtered_team_config.items()))

    def sync_current_teams_settings(self, dry: bool = False) -> None:
        """Sync settings for the existing teams: description, visibility etc."""
        for team in self.current_teams:
            # Skip unconfigured teams
            if team.name not in self.configured_teams:
                logging.debug(
                    "Will not sync settings of team '%s' as not configured locally", team.name
                )
                continue

            # Use dictionary comprehensions to build the dictionaries with the
            # relevant team settings for comparison
            configured_team_configs = {
                key: self.configured_teams[team.name].get(key)  # type: ignore
                for key in self.TEAM_CONFIG_FIELDS
                # Only add keys that are actually in the configuration. Deals
                # with settings that should be changed, as they are neither
                # defined in the default or team config, and marked as
                # <keep-current>
                if key in self.configured_teams[team.name]  # type: ignore
            }
            current_team_configs = {
                key: getattr(team, key)
                for key in self.TEAM_CONFIG_FIELDS
                # Only compare current team settings with keys that are defined
                # as the configured team settings. Taking out settings that
                # shall not be changed
                if key in self.configured_teams[team.name]  # type: ignore
            }

            # Resolve parent team id from parent Team object or team string, and sort
            configured_team_configs = self._prepare_team_config_for_sync(configured_team_configs)
            current_team_configs = self._prepare_team_config_for_sync(current_team_configs)

            # Log the comparison result
            logging.debug(
                "Comparing team '%s' settings: Configured '%s' vs. Current '%s'",
                team.name,
                configured_team_configs,
                current_team_configs,
            )

            # Compare settings and update if necessary
            if differences := self.compare_two_dicts(configured_team_configs, current_team_configs):
                # Log differences
                logging.info(
                    "Team settings for '%s' differ from the configuration. Updating them:",
                    team.name,
                )
                for setting, diff in differences.items():
                    logging.info(
                        "Setting '%s': '%s' --> '%s'", setting, diff["dict2"], diff["dict1"]
                    )
                # Execute team setting changes
                if not dry:
                    try:
                        team.edit(name=team.name, **configured_team_configs)  # type: ignore
                    except GithubException as exc:
                        logging.critical(
                            "Team '%s' settings could not be edited. Error: \n%s",
                            team.name,
                            self.pretty_print_dict(exc.data),
                        )
                        sys.exit(1)
            else:
                logging.info("Team '%s' settings are in sync, no changes", team.name)

    # --------------------------------------------------------------------------
    # Members
    # --------------------------------------------------------------------------
    def _get_current_org_members(self):
        """Get all ordinary members of the org"""
        # Reset the user list, then build up new list
        self.org_members = []
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

    def _get_current_team_members(self, team: Team) -> dict[NamedUser, str]:
        """Return dict of current users with their respective roles. Also
        contains members of child teams"""
        current_users: dict[NamedUser, str] = {}
        for role in ("member", "maintainer"):
            # Make a two-step check whether person is actually in team, as
            # get_members() also return child-team members
            for user in list(team.get_members(role=role)):
                current_users.update({user: role})

        return current_users

    def _add_or_update_user_in_team(self, team: Team, user: NamedUser, role: str):
        """Add or update membership of a user in a team"""
        team.add_membership(member=user, role=role)
        # Document that the user has just been added to a team. Relevant when we
        # will later find users without team membership
        self.newly_added_users.append(user)

    def sync_teams_members(self, dry: bool = False) -> None:  # pylint: disable=too-many-branches
        """Check the configured members of each team, add missing ones and delete unconfigured"""
        logging.debug("Starting to sync team members")

        # Gather all ordinary members of the organisation
        self._get_current_org_members()

        # Get open invitations
        open_invitations = [user.login.lower() for user in self.org.invitations()]

        for team, team_attrs in self.current_teams.items():
            # Update current team members with dict[NamedUser, str (role)]
            team_attrs["members"] = self._get_current_team_members(team)

            # For the rest of the function however, we use just the login name
            # for each current user. All lower-case
            current_team_members = {
                user.login.lower(): role for user, role in team_attrs["members"].items()
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

            # Analog to team_attrs["members"], add members and maintainers to
            # shared dict with respective role, while maintainer role dominates.
            # All user names shall be lower-case to ease comparison
            configured_users: dict[str, str] = {}
            for config_role in ("member", "maintainer"):
                team_members = self._get_configured_team_members(
                    team_configuration, team.name, config_role
                )
                for team_member in team_members:
                    # Add user with role to dict, in lower-case
                    configured_users.update({team_member.lower(): config_role})

            # Consider all GitHub organisation team maintainers if they are member of the team
            # This is because GitHub API returns them as maintainers even if they are just members
            for user in self.current_org_owners:
                if user.login in configured_users:
                    logging.debug(
                        "Overriding role of organisation owner '%s' to maintainer", user.login
                    )
                    configured_users[user.login.lower()] = "maintainer"

            # Only make edits to the team membership if the current state differs from config
            if configured_users == current_team_members:
                logging.info("Team '%s' memberships are in sync, no changes", team.name)
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
                        self._add_or_update_user_in_team(team=team, user=gh_user, role=config_role)

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
                        self._add_or_update_user_in_team(team=team, user=gh_user, role=config_role)

            # Loop through all current members. Remove them if they are not configured
            for current_user in current_team_members:
                if current_user not in configured_users:
                    logging.debug("User '%s' not found within configured users", current_user)
                    # Turn user to GitHub object, trying to find them
                    if not (gh_user := self._resolve_gh_username(current_user, team.name)):
                        # If the user cannot be found for some reason, log an
                        # error and skip this loop
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
        all_org_members = set(self.org_members + self.current_org_owners)

        # Get all members of all teams
        all_team_members_lst: list[NamedUser] = []
        for _, team_attrs in self.current_teams.items():
            for member in team_attrs.get("members", {}):
                all_team_members_lst.append(member)
        # Also add users that have just been added to a team, and unify them
        all_team_members: set[NamedUser] = set(all_team_members_lst + self.newly_added_users)

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
    def _get_current_repos_and_team_perms(self, ignore_archived: bool) -> None:
        """Get all repos, their current teams and their permissions"""
        for repo in list(self.org.get_repos()):
            # Check if repo is archived. If so, ignore it, if user requested so
            if ignore_archived and repo.archived:
                logging.debug(
                    "Ignoring %s as it is archived and user requested to ignore such repos",
                    repo.name,
                )
                self.archived_repos.append(repo)
                continue

            self.current_repos_teams[repo] = {}
            for team in list(repo.get_teams()):
                self.current_repos_teams[repo][team] = team.permission

    def _create_perms_changelist_for_teams(
        self,
    ) -> dict[Team, dict[Repository, str]]:
        """Create a permission/repo changelist from the perspective of configured teams"""
        team_changelist: dict[Team, dict[Repository, str]] = {}
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

                if perm != self.current_repos_teams[repo].get(team):
                    # Add the changeset to the changelist
                    if team not in team_changelist:
                        team_changelist[team] = {}
                    team_changelist[team][repo] = perm

        return team_changelist

    def _document_unconfigured_team_repo_permissions(
        self, team: Team, team_permission: str, repo_name: str
    ) -> None:
        """Create a record of all members of a team and their permissions on a
        repo due to being member of an unconfigured team"""
        users_of_unconfigured_team: dict[NamedUser, str] = self.current_teams[team].get(
            "members"
        )  # type: ignore
        # Initiate this repo in the dict as dict if not present
        if repo_name not in self.unconfigured_team_repo_permissions:
            self.unconfigured_team_repo_permissions[repo_name] = {}
        # Add actual permission for each user of this unconfigured team
        for user in users_of_unconfigured_team:
            # Handle if another, potentially higher permission is already set by
            # membership in another team
            if exist_perm := self.unconfigured_team_repo_permissions[repo_name].get(user.login, ""):
                logging.debug(
                    "Permissions for %s on %s already exist: %s. "
                    "Checking whether new permission is higher.",
                    user.login,
                    repo_name,
                    exist_perm,
                )
                self.unconfigured_team_repo_permissions[repo_name][user.login] = (
                    self._get_highest_permission(exist_perm, team_permission)
                )
            else:
                self.unconfigured_team_repo_permissions[repo_name][user.login] = team_permission

    def sync_repo_permissions(self, dry: bool = False, ignore_archived: bool = False) -> None:
        """Synchronise the repository permissions of all teams"""
        logging.debug("Starting to sync repo/team permissions")

        # Get all repos and their current permissions from GitHub
        self._get_current_repos_and_team_perms(ignore_archived)

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
        for repo, teams in self.current_repos_teams.items():
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
                    # Store information about these team members and their
                    # permissions on the repo. We will use it later in the
                    # collaborators step
                    self._document_unconfigured_team_repo_permissions(
                        team=team, team_permission=teams[team], repo_name=repo.name
                    )
                    # Abort handling the repo sync as we don't touch unconfigured teams
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

    # --------------------------------------------------------------------------
    # Collaborators
    # --------------------------------------------------------------------------
    def _aggregate_lists(self, *lists: list[str | int]) -> list[str | int]:
        """Combine multiple lists into one while removing duplicates"""
        complete = []
        for single_list in lists:
            if single_list is not None:
                complete.extend(single_list)
            else:
                logging.debug(
                    "A list that we attempted to extend to another was None. "
                    "This probably happened because a 'member:' or 'maintainer:' key was left empty"
                )

        return list(set(complete))

    def _get_highest_permission(self, *permissions: str) -> str:
        """Get the highest GitHub repo permissions out of multiple permissions"""
        perms_ranking = ["admin", "maintain", "push", "triage", "pull"]
        for perm in perms_ranking:
            # If e.g. "maintain" matches one of the two permissions
            if perm in permissions:
                logging.debug("%s is the highest permission", perm)
                return perm

        return ""

    def _get_direct_repo_permissions_of_team(self, team_dict: dict) -> tuple[dict[str, str], str]:
        """Get a list of directly configured repo permissions for a team, and
        whether the team has a parent"""
        repo_perms: dict[str, str] = {}
        # Direct permissions
        for repo, perm in team_dict.get("repos", {}).items():
            repo_perms[repo] = perm

        # Parent team
        parent = team_dict.get("parent", "")

        return repo_perms, parent

    def _get_all_repo_permissions_for_team_and_parents(self, team_name: str, team_dict: dict):
        """Get a list of all configured repo permissions for a team, also those
        inherited by parent teams"""
        all_repo_perms, parent = self._get_direct_repo_permissions_of_team(team_dict=team_dict)
        # If parents have been found, iterate and merge them
        while parent:
            logging.debug(
                "Checking for repository permissions of %s's parent team %s", team_name, parent
            )
            parent_team_dict = self.configured_teams[parent]

            # Handle empty parent dict
            if not parent_team_dict:
                break

            # Get repo permissions and potential parent, and add it
            repo_perm, parent = self._get_direct_repo_permissions_of_team(
                team_dict=parent_team_dict
            )
            for repo, perm in repo_perm.items():
                # Add (highest) repo permission
                all_repo_perms[repo] = self._get_highest_permission(
                    perm, all_repo_perms.get(repo, "")
                )

        return all_repo_perms

    def _get_configured_repos_and_user_perms(self):
        """
        Get a list of repos with a list of individuals and their permissions,
        based on their team memberships
        """
        for team_name, team_attrs in self.configured_teams.items():
            logging.debug("Getting configured repository permissions for team %s", team_name)
            repo_perms = self._get_all_repo_permissions_for_team_and_parents(team_name, team_attrs)
            for repo, perm in repo_perms.items():
                # Create repo if non-exist
                if repo not in self.configured_repos_collaborators:
                    self.configured_repos_collaborators[repo] = {}

                # Get team maintainers and members
                team_members = self._aggregate_lists(
                    team_attrs.get("maintainer", []), team_attrs.get("member", [])
                )

                # Add team member to repo with their repo permissions
                for team_member in team_members:
                    # Lower-case team member
                    team_member = team_member.lower()
                    # Check if permissions already exist
                    if self.configured_repos_collaborators[repo].get(team_member, {}):
                        logging.debug(
                            "Permissions for %s on %s already exist: %s. "
                            "Checking whether new permission is higher.",
                            team_member,
                            repo,
                            self.configured_repos_collaborators[repo][team_member],
                        )
                        self.configured_repos_collaborators[repo][team_member] = (
                            self._get_highest_permission(
                                perm, self.configured_repos_collaborators[repo][team_member]
                            )
                        )
                    else:
                        self.configured_repos_collaborators[repo][team_member] = perm

    def _convert_graphql_perm_to_rest(self, permission: str) -> str:
        """Convert a repo permission coming from the GraphQL API to the ones
        coming from the REST API"""
        perm_conversion = {
            "none": "",
            "read": "pull",
            "triage": "triage",
            "write": "push",
            "maintain": "maintain",
            "admin": "admin",
        }
        if permission.lower() in perm_conversion:
            replacement = perm_conversion.get(permission.lower(), "")
            return replacement

        return permission

    def _fetch_collaborators_of_repo(self, repo: Repository):
        """Get all collaborators (individuals) of a GitHub repo with their
        permissions using the GraphQL API"""
        # TODO: Consider doing this for all repositories at once, but calculate
        # costs beforehand
        query = """
            query($owner: String!, $name: String!, $cursor: String) {
                repository(owner: $owner, name: $name) {
                    collaborators(first: 100, after: $cursor) {
                        edges {
                            node {
                                login
                            }
                            permission
                        }
                        pageInfo {
                            endCursor
                            hasNextPage
                        }
                }
            }
        }
        """

        # Initial query parameters
        variables = {"owner": self.org.login, "name": repo.name, "cursor": None}

        collaborators = []
        has_next_page = True

        while has_next_page:
            logging.debug("Requesting collaborators for %s", repo.name)
            result = run_graphql_query(query, variables, self.gh_token)
            try:
                collaborators.extend(result["data"]["repository"]["collaborators"]["edges"])
                has_next_page = result["data"]["repository"]["collaborators"]["pageInfo"][
                    "hasNextPage"
                ]
                variables["cursor"] = result["data"]["repository"]["collaborators"]["pageInfo"][
                    "endCursor"
                ]
            except (TypeError, KeyError):
                logging.debug("Repo %s does not seem to have any collaborators", repo.name)
                continue

        # Extract relevant data
        for collaborator in collaborators:
            login: str = collaborator["node"]["login"]
            # Skip entry if collaborator is org owner, which is "admin" anyway
            if login.lower() in [user.login.lower() for user in self.current_org_owners]:
                continue
            permission = self._convert_graphql_perm_to_rest(collaborator["permission"])
            self.current_repos_collaborators[repo][login.lower()] = permission

    def _get_current_repos_and_user_perms(self):
        """Get all repos, their current collaborators and their permissions"""
        # We copy the list of repos from self.current_repos_teams
        for repo in self.current_repos_teams:
            self.current_repos_collaborators[repo] = {}

        for repo in self.current_repos_collaborators:
            # Get users for this repo
            self._fetch_collaborators_of_repo(repo)

    def _get_default_repository_permission(self):
        """Get the default repository permission for all users. Convert to
        admin/maintain/push/triage/pull scheme that the REST API provides"""
        self.default_repository_permission = self._convert_graphql_perm_to_rest(
            self.org.default_repository_permission
        )

    def _permission1_higher_than_permission2(self, permission1: str, permission2: str) -> bool:
        """Check whether permission 1 is higher than permission 2"""
        perms_ranking = ["admin", "maintain", "push", "triage", "pull", ""]

        def get_rank(permission):
            return perms_ranking.index(permission) if permission in perms_ranking else 99

        rank_permission1 = get_rank(permission1)
        rank_permission2 = get_rank(permission2)

        # The lower the index, the higher the permission. If lower than
        # permission2, return True
        return rank_permission1 < rank_permission2

    def sync_repo_collaborator_permissions(self, dry: bool = False):
        """Compare the configured with the current repo permissions for all
        repositories' collaborators"""
        # Collect info about all repos, their configured collaborators (through
        # team membership) and the current state (either through team membership
        # or individual).
        # The resulting structure is:
        # - configured_repos_collaborators: dict[Repository, dict[username, permission]]
        # - current_repos_collaborators: dict[Repository, dict[username, permission]]
        logging.debug("Starting to sync collaborator/individual permissions")
        self._get_configured_repos_and_user_perms()
        self._get_current_repos_and_user_perms()

        # Get and convert the default permission for all members so we can check for it
        self._get_default_repository_permission()

        # Loop over all factually existing repositories. This will be a one-way
        # sync. Team permissions have been set before, we are now removing
        # surplus permissions. As no individual permissions are allowed, these
        # will be fully revoked.
        for repo, current_repo_perms in self.current_repos_collaborators.items():
            for username, current_perm in current_repo_perms.items():
                # Get configured user permissions for this repo
                try:
                    config_perm = self.configured_repos_collaborators[repo.name][username]
                # There is no configured permission for this user in this repo,
                # so we assume the default permission
                except KeyError:
                    config_perm = self.default_repository_permission

                # Evaluate whether current permission is higher than configured
                # permission
                if self._permission1_higher_than_permission2(current_perm, config_perm):
                    # Find out whether user has these unconfigured permissions
                    # due to being member of an unconfigured team. Check whether
                    # these are the same permissions as the team would get them.
                    unconfigured_team_repo_permission = self.unconfigured_team_repo_permissions.get(
                        repo.name, {}
                    ).get(username, "")

                    if unconfigured_team_repo_permission:
                        if current_perm == unconfigured_team_repo_permission:
                            logging.info(
                                "User %s has '%s' permission on repo '%s' due to being member of "
                                "an unconfigured team, and this matches their current permission. "
                                "Will not make any changes therefore.",
                                username,
                                current_perm,
                                repo.name,
                            )
                            continue

                        logging.info(
                            "User %s should have '%s' permissions on repo '%s' due to being member "
                            "of an unconfigured team, but their current permission on the "
                            "repo is '%s'. Removing them from collaborators therefore.",
                            username,
                            unconfigured_team_repo_permission,
                            repo.name,
                            current_perm,
                        )

                    # Remove person from repo, but only if their repository also
                    # diverges from the default repository permission given by
                    # the organization
                    logging.info(
                        "Remove %s from %s. They have '%s' there but should only have '%s'.",
                        username,
                        repo.name,
                        current_perm,
                        config_perm,
                    )

                    # Remove collaborator
                    if not dry:
                        repo.remove_from_collaborators(username)
