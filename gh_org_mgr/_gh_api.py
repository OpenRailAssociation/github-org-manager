# SPDX-FileCopyrightText: 2024 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""
Functions for interacting with the GitHub API
"""

import logging
import os
import sys


def get_github_token(token: str = "") -> str:
    """Get the GitHub token from config or environment, while environment overrides"""
    if "GITHUB_TOKEN" in os.environ and os.environ["GITHUB_TOKEN"]:
        logging.debug("GitHub Token taken from environment variable GITHUB_TOKEN")
        token = os.environ["GITHUB_TOKEN"]
    elif token:
        logging.debug("GitHub Token taken from app configuration file")
    else:
        sys.exit(
            "No token set for GitHub authentication! Set it in config/app_config.yaml "
            "or via environment variable GITHUB_TOKEN"
        )

    return token
