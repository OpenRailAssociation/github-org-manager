# SPDX-FileCopyrightText: 2025 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Dataclasses and functions for statistics"""

import json
from dataclasses import dataclass, field

from ._helpers import implement_changes_into_class


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

    dry: bool = False
    added_owners: list[str] = field(default_factory=list)
    degraded_owners: list[str] = field(default_factory=list)
    members_without_team: list[str] = field(default_factory=list)
    removed_members: list[str] = field(default_factory=list)
    teams: dict[str, TeamChanges] = field(default_factory=dict)
    repos: dict[str, RepoChanges] = field(default_factory=dict)

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

        implement_changes_into_class(dc_object=self.teams[team_name], **changes)

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

        implement_changes_into_class(dc_object=self.repos[repo_name], **changes)

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

    # --------------------------------------------------------------------------
    # Output
    # --------------------------------------------------------------------------
    def changes_into_dict(self) -> dict:
        """Convert dataclass to dict, and only use classes that are not empty/False"""
        changes_dict: dict[str, list[str] | dict] = {
            key: value  # type: ignore
            for key, value in {
                "dry": self.dry,
                "added_owners": self.added_owners,
                "degraded_owners": self.degraded_owners,
                "members_without_team": self.members_without_team,
                "removed_members": self.removed_members,
                "teams": self.teams,
                "repos": self.repos,
            }.items()
            if value  # Exclude empty values
        }

        team_changes: dict[str, TeamChanges] = changes_dict.get("teams", {})  # type: ignore
        repo_changes: dict[str, RepoChanges] = changes_dict.get("repos", {})  # type: ignore

        for team, tchanges in team_changes.items():
            new_changes = {
                key: value
                for key, value in tchanges.__dict__.items()
                if value  # Exclude empty values
            }
            team_changes[team] = new_changes  # type: ignore
        changes_dict["teams"] = team_changes

        for repo, rchanges in repo_changes.items():
            new_changes = {
                key: value
                for key, value in rchanges.__dict__.items()
                if value  # Exclude empty values
            }
            repo_changes[repo] = new_changes  # type: ignore
        changes_dict["repos"] = repo_changes

        return changes_dict

    def print_changes(  # pylint: disable=too-many-branches, too-many-statements
        self, orgname: str, output: str, dry: bool
    ) -> None:
        """Print the changes, either in pretty format or as JSON"""

        # Add dry run information to stats dataclass
        self.dry = dry

        # Output in the requested format
        if output == "json":
            changes_dict = self.changes_into_dict()
            print(json.dumps(changes_dict, indent=2))
        else:
            output = (
                f"#-------------------------------------{len(orgname)*'-'}\n"
                f"# Changes made to GitHub organisation {orgname}\n"
                f"#-------------------------------------{len(orgname)*'-'}\n\n"
            )
            if dry:
                output += "⚠️ Dry-run mode, no changes executed\n\n"
            if self.added_owners:
                output += f"➕ Added owners: {', '.join(self.added_owners)}\n"
            if self.degraded_owners:
                output += f"🔻 Degraded owners: {', '.join(self.degraded_owners)}\n"
            if self.members_without_team:
                output += f"⚠️ Members without team: {', '.join(self.members_without_team)}\n"
            if self.removed_members:
                output += (
                    f"❌ Members removed from organisation: {', '.join(self.removed_members)}\n"
                )
            if self.teams:
                output += "\n🤝 Team Changes:\n"
                for team, tchanges in self.teams.items():
                    output += f"  🔹 {team}:\n"
                    if tchanges.unconfigured:
                        output += "    ⚠️ Is/was unconfigured\n"
                    if tchanges.newly_created:
                        output += "    🆕 Has been created\n"
                    if tchanges.deleted:
                        output += "    ❌ Has been deleted\n"
                    if tchanges.changed_config:
                        output += "    🔧 Changed config:\n"
                        for item in tchanges.changed_config:
                            output += f"      - {item}\n"
                    if tchanges.added_members:
                        output += "    ➕ Added members:\n"
                        for item in tchanges.added_members:
                            output += f"      - {item}\n"
                    if tchanges.changed_members_role:
                        output += '    🔄 Changed members role:"'
                        for item in tchanges.changed_members_role:
                            output += f"      - {item}\n"
                    if tchanges.removed_members:
                        output += "    ❌ Removed members:\n"
                        for item in tchanges.removed_members:
                            output += f"      - {item}\n"
                    if tchanges.pending_members:
                        output += "    ⏳ Pending members:\n"
                        for item in tchanges.pending_members:
                            output += f"      - {item}\n"
            if self.repos:
                output += "\n📂 Repository Changes:\n"
                for repo, rchanges in self.repos.items():
                    output += f"  🔹 {repo}:\n"
                    if rchanges.changed_permissions_for_teams:
                        output += "    🔧 Changed permissions for teams:\n"
                        for item in rchanges.changed_permissions_for_teams:
                            output += f"      - {item}\n"
                    if rchanges.removed_teams:
                        output += "    ❌ Removed teams:\n"
                        for item in rchanges.removed_teams:
                            output += f"      - {item}\n"
                    if rchanges.unconfigured_teams_with_permissions:
                        output += "    ⚠️ Unconfigured teams with permissions:\n"
                        for item in rchanges.unconfigured_teams_with_permissions:
                            output += f"      - {item}\n"
                    if rchanges.removed_collaborators:
                        output += "    ❌ Removed collaborators:\n"
                        for item in rchanges.removed_collaborators:
                            output += f"      - {item}\n"

            print(output.strip())
