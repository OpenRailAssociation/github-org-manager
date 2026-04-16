# SPDX-FileCopyrightText: 2024 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Functions for interacting with the GitHub API."""

import contextlib
import logging
import os
import sys
from http import HTTPStatus
from typing import Any

import requests


def get_github_secrets_from_env(env_variable: str, secret: str | int) -> str:
    """Get GitHub secrets from config or environment, while environment overrides."""
    if os.environ.get(env_variable):
        logging.debug("GitHub secret taken from environment variable %s", env_variable)
        secret = os.environ[env_variable]
    elif secret:
        logging.debug("GitHub secret taken from app configuration file")

    return str(secret)


# Function to execute GraphQL query
def run_graphql_query(query: str, variables: dict[str, Any], token: str) -> dict | str:
    """Run a query against the GitHub GraphQL API."""
    headers = {"Authorization": f"Bearer {token}"}
    request = requests.post(
        "https://api.github.com/graphql",
        json={"query": query, "variables": variables},
        headers=headers,
        timeout=10,
    )

    # Get JSON result
    json_return = "No valid JSON return"
    with contextlib.suppress(requests.exceptions.JSONDecodeError):
        json_return = request.json()

    if request.status_code == HTTPStatus.OK:
        return json_return

    # Debug information in case of errors
    logging.error(
        "Query failed with HTTP error code '%s' when running this query: %s\n"
        "Return: %s\nHeaders: %s",
        request.status_code,
        query,
        json_return,
        request.headers,
    )
    sys.exit(1)
