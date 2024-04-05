"""Manage people in GitHub Organization"""

from dataclasses import dataclass, field

from github import Github

from .ghapi import get_github_token

ORG = "OpenRailAssociation"


@dataclass
class GHorg:
    """Dataclass holding GH organization data and functions"""

    org = None
    members: list[str] = field(default_factory=list)

    def login(self, orgname):
        """Login to GH, gather org data"""
        self.org = Github(get_github_token()).get_organization(orgname)

    def build_members(self):
        """Get all current members of the org"""
        for member in self.org.get_members():
            self.members.append(member.login)


def main():
    """Main function"""
    org = GHorg()
    org.login(ORG)
    org.build_members()

    print(org)
