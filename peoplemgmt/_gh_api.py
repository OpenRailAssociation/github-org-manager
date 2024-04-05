"""
Functions for interacting with the GitHub API
"""

import os
import sys

from ._config import get_app_config


def get_github_token() -> str:
    """Get the GitHub token from config or environment, while environment overrides"""
    if "GITHUB_TOKEN" in os.environ and os.environ["GITHUB_TOKEN"]:
        token = os.environ["GITHUB_TOKEN"]
    elif get_app_config("GITHUB_TOKEN"):
        token = get_app_config("GITHUB_TOKEN")
    else:
        sys.exit(
            "No token set for GitHub authentication! Set it in config/app_config.yaml "
            "or via environment variable GITHUB_TOKEN"
        )

    return token
