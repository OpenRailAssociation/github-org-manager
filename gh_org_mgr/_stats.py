# SPDX-FileCopyrightText: 2025 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Dataclasses and functions for statistics"""

from dataclasses import dataclass, field


@dataclass
class TeamChanges:  # pylint: disable=too-many-instance-attributes
    """Dataclass holding information about the changes made to a team"""

    newly_created: bool = False
    deleted: bool = False
    unconfigured: bool = False
    changed_config: list[str] = field(default_factory=list)
    added_members: list[str] = field(default_factory=list)
    changed_members_role: list[str] = field(default_factory=list)
    removed_members: list[str] = field(default_factory=list)
    pending_members: list[str] = field(default_factory=list)


@dataclass
class RepoChanges:  # pylint: disable=too-many-instance-attributes
    """Dataclass holding information about the changes made to a repository"""

    changed_permissions_for_teams: list[str] = field(default_factory=list)
    removed_teams: list[str] = field(default_factory=list)
    unconfigured_teams_with_permissions: list[str] = field(default_factory=list)
    removed_collaborators: list[str] = field(default_factory=list)


@dataclass
class OrgChanges:  # pylint: disable=too-many-instance-attributes
    """Dataclass holding general statistics about the changes made to the organization"""

    added_owners: list[str] = field(default_factory=list)
    degraded_owners: list[str] = field(default_factory=list)
    teams: dict[str, TeamChanges] = field(default_factory=dict)
    repos: dict[str, RepoChanges] = field(default_factory=dict)
    members_without_team: list[str] = field(default_factory=list)
    removed_members: list[str] = field(default_factory=list)

    # --------------------------------------------------------------------------
    # Owners
    # --------------------------------------------------------------------------
    def add_owner(self, user: str) -> None:
        """User has been added as owner"""
        self.added_owners.append(user)

    def degrade_owner(self, user: str) -> None:
        """User has been degraded from owner to member"""
        self.degraded_owners.append(user)

    # --------------------------------------------------------------------------
    # Teams
    # --------------------------------------------------------------------------
    def update_team(self, team_name: str, **changes: bool | str | list[str]) -> None:
        """Update team changes"""
        # Initialise team if not present
        if team_name not in self.teams:
            self.teams[team_name] = TeamChanges()

        implement_changes(dc_object=self.teams[team_name], **changes)

    def create_team(self, team: str) -> None:
        """Team has been created"""
        self.update_team(team_name=team, newly_created=True)

    def edit_team_config(self, team: str, new_config: str) -> None:
        """Team config has been changed"""
        self.update_team(team_name=team, changed_config=new_config)

    def delete_team(self, team: str, deleted: bool) -> None:
        """Teams are not configured"""
        self.update_team(team_name=team, unconfigured=True, deleted=deleted)

    # --------------------------------------------------------------------------
    # Members
    # --------------------------------------------------------------------------
    def add_team_member(self, team: str, user: str) -> None:
        """User has been added to team"""
        self.update_team(team_name=team, added_members=user)

    def change_team_member_role(self, team: str, user: str) -> None:
        """User role has been changed in team"""
        self.update_team(team_name=team, changed_members_role=user)

    def pending_team_member(self, team: str, user: str) -> None:
        """User has a pending invitation"""
        self.update_team(team_name=team, pending_members=user)

    def remove_team_member(self, team: str, user: str) -> None:
        """User has been removed from team"""
        self.update_team(team_name=team, removed_members=user)

    def remove_member_without_team(self, user: str, removed: bool) -> None:
        """User is not in any team"""
        self.members_without_team.append(user)
        if removed:
            self.removed_members.append(user)

    # --------------------------------------------------------------------------
    # Repos
    # --------------------------------------------------------------------------
    def update_repo(self, repo_name: str, **changes: bool | str | list[str]) -> None:
        """Update team changes"""
        # Initialise repo if not present
        if repo_name not in self.teams:
            self.repos[repo_name] = RepoChanges()

        implement_changes(dc_object=self.repos[repo_name], **changes)

    def change_repo_team_permissions(self, repo: str, team: str, perm: str) -> None:
        """Team permissions have been changed for a repo"""
        self.update_repo(repo_name=repo, changed_permissions_for_teams=f"{team}: {perm}")

    def remove_team_from_repo(self, repo: str, team: str) -> None:
        """Team has been removed form a repo"""
        self.update_repo(repo_name=repo, removed_teams=team)

    def document_unconfigured_team_permissions(self, repo: str, team: str, perm: str) -> None:
        """Unconfigured team has permissions on repo"""
        self.update_repo(repo_name=repo, unconfigured_teams_with_permissions=f"{team}: {perm}")

    def remove_repo_collaborator(self, repo: str, user: str) -> None:
        """Remove collaborator"""
        self.update_repo(repo_name=repo, removed_collaborators=user)


def implement_changes(dc_object, **changes: bool | str | list[str]):
    """Smartly add changes to a dataclass object"""
    for attribute, value in changes.items():
        current_value = getattr(dc_object, attribute)
        # attribute is list
        if isinstance(current_value, list):
            # input change is list
            if isinstance(value, list):
                current_value.extend(value)
            # input change is not list
            else:
                current_value.append(value)
        # All other cases, bool
        else:
            setattr(dc_object, attribute, value)

    return dc_object
