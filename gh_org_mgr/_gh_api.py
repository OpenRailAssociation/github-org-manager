# SPDX-FileCopyrightText: 2024 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""
Functions for interacting with the GitHub API
"""

import logging
import os
import sys

import requests


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


# Function to execute GraphQL query
def run_graphql_query(query, variables, token):
    """Run a query against the GitHub GraphQL API"""
    headers = {"Authorization": f"Bearer {token}"}
    request = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=10,
    )

    # Get JSON result
    json_return = "No valid JSON return"
    try:
        json_return = request.json()
    except requests.exceptions.JSONDecodeError:
        pass

    if request.status_code == 200:
        return json_return

    # Debug information in case of errors
    print(
        f"Query failed with HTTP error code '{request.status_code}' when running "
        f"this query: {query}\n"
        f"Return: {json_return}\n"
        f"Headers: {request.headers}"
    )
    sys.exit(1)
