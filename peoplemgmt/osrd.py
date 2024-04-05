"""Manage people in GitHub Organization"""

from dataclasses import dataclass, field

from github import Github

from .ghapi import get_github_token

from .config import get_config

ORG = "OpenRailAssociation"


@dataclass
class GHorg:
    """Dataclass holding GH organization data and functions"""

    org = None
    current_members: list[str] = field(default_factory=list)
    configured_members: dict[str, dict] = field(default_factory=dict)

    def login(self, orgname):
        """Login to GH, gather org data"""
        self.org = Github(get_github_token()).get_organization(orgname)

    def get_current_members(self):
        """Get all current members of the org"""
        for member in self.org.get_members():
            self.current_members.append(member.login)

    def read_configured_members(self):
        """Import configured members of the org"""
        self.configured_members = get_config("config/openrailassociation.yaml", "members")

        for member, v in self.configured_members.items():
            print(member)
            print(v)


def main():
    """Main function"""
    org = GHorg()
    org.login(ORG)
    org.get_current_members()
    org.read_configured_members()

    # print(org)
