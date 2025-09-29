# SPDX-FileCopyrightText: 2024 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Handling the private and organisation configuration"""

import logging
import os
import re
import sys
from typing import Any

import yaml
from jsonschema import FormatChecker, validate
from jsonschema.exceptions import ValidationError

# Global files with settings for the app and org, e.g. GitHub token and org name
ORG_CONFIG_FILE = r"org\.ya?ml"
APP_CONFIG_FILE = r"app\.ya?ml"
TEAM_CONFIG_DIR = "teams"
TEAM_CONFIG_FILES = r".+\.ya?ml"

# Schemas for config validation
APP_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "github_token": {"type": "string"},
        "github_app_id": {"type": "integer"},
        "github_app_private_key": {"type": "string"},
        "remove_members_without_team": {"type": "boolean"},
        "delete_unconfigured_teams": {"type": "boolean"},
    },
    "additionalProperties": False,
}
ORG_CONFIG_SCHEMA = {
    "type": "object",
    "properties": {
        "org_name": {"type": "string"},
        "org_owners": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "defaults": {
            "type": "object",
            "properties": {
                "team": {
                    "type": "object",
                    "properties": {
                        "description": {"type": "string"},
                        "privacy": {"type": "string", "enum": ["secret", "closed"]},
                        "notification_setting": {
                            "type": "string",
                            "enum": ["notifications_enabled", "notifications_disabled"],
                        },
                    },
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        },
    },
    "additionalProperties": False,
    "required": ["org_name", "org_owners"],
}
TEAM_CONFIG_SCHEMA = {
    "type": "object",
    "patternProperties": {
        "^[a-zA-Z0-9 _\\-]+$": {
            "type": "object",
            "properties": {
                "description": {"type": "string"},
                "privacy": {"type": "string", "enum": ["secret", "closed"]},
                "notification_setting": {
                    "type": "string",
                    "enum": ["notifications_enabled", "notifications_disabled"],
                },
                "maintainer": {
                    "oneOf": [{"type": "null"}, {"type": "array", "items": {"type": "string"}}]
                },
                "member": {
                    "oneOf": [{"type": "null"}, {"type": "array", "items": {"type": "string"}}]
                },
                "parent": {"type": "string"},
                "repos": {
                    "type": "object",
                    "propertyNames": {"type": "string"},
                    "additionalProperties": {
                        "type": "string",
                        "enum": ["pull", "triage", "push", "maintain", "admin"],
                    },
                },
            },
            "additionalProperties": False,
        }
    },
    "additionalProperties": False,
    "required": [],
}


def _find_matching_files(directory: str, pattern: str, only_one: bool = False) -> list[str]:
    """
    Get all files in a directory matching a regex pattern.

    Args:
    - directory: Path to the directory
    - pattern: Regular expression pattern to match filenames
    - only_one: Whether only the first match shall be returned.

    Returns:
    - List of filenames matching the pattern
    """
    matching_files: list[str] = []

    # Validate directory existence
    if not os.path.isdir(directory):
        logging.error("'%s' is not a valid directory", directory)

    else:
        # Compile the regex pattern
        regex_pattern = re.compile(pattern + "$")

        # Traverse the directory and find matching files
        for file_name in os.listdir(directory):
            if regex_pattern.match(file_name):
                file_path = os.path.join(directory, file_name)
                if os.path.isfile(file_path):
                    matching_files.append(file_path)
                else:
                    logging.warning(
                        "'%s' looks like a file we searched for, but it's not. "
                        "Will not consider its contents",
                        file_path,
                    )

        if only_one and len(matching_files) > 1:
            matching_files = [matching_files[0]]
            logging.warning(
                "More than one configuration file for the pattern '%s' found. "
                "Reducing to the first match as wished: %s",
                pattern,
                matching_files[0],
            )

    if not matching_files:
        logging.error(
            "No configuration file found for '%s' in '%s'. The program might not work as expected!",
            pattern,
            directory,
        )

    return matching_files


def _read_config_file(file: str) -> dict:
    """Return dict of a YAML file"""
    logging.debug("Attempting to parse YAML file %s", file)
    with open(file, encoding="UTF-8") as yamlfile:
        config: dict = yaml.safe_load(yamlfile)

    if not config:
        config = {}

    return config


def _validate_config_schema(file: str, cfg: dict, schema: dict) -> None:
    """Validate the config against a JSON schema"""
    try:
        validate(instance=cfg, schema=schema, format_checker=FormatChecker())
    except ValidationError as e:
        logging.critical("Config validation of file %s failed: %s", file, e.message)
        raise ValueError(e) from None
    logging.debug("Config in file %s validated successfully against schema.", file)


def parse_config_files(path: str) -> tuple[dict[str, str | dict[str, str]], dict, dict]:
    """Parse all relevant files in the configuration directory. Returns a tuple
    of org config, app config, and merged teams config"""
    # Find the relevant config files for app, org, and teams
    cfg_app_files = _find_matching_files(path, APP_CONFIG_FILE, only_one=True)
    cfg_org_files = _find_matching_files(path, ORG_CONFIG_FILE, only_one=True)
    cfg_teams_files = _find_matching_files(os.path.join(path, TEAM_CONFIG_DIR), TEAM_CONFIG_FILES)

    # Read and parse config files for app and org
    cfg_app = _read_config_file(cfg_app_files[0])
    _validate_config_schema(file=cfg_app_files[0], cfg=cfg_app, schema=APP_CONFIG_SCHEMA)
    cfg_org = _read_config_file(cfg_org_files[0])
    _validate_config_schema(file=cfg_org_files[0], cfg=cfg_org, schema=ORG_CONFIG_SCHEMA)

    # For the teams config files, we parse and combine them as there may be multiple
    cfg_teams: dict[str, Any] = {}
    # For this, merge the resulting dicts of the previously read files, and the current file
    # Compare their keys (team names). They must not be defined multiple times!
    for cfg_team_file in cfg_teams_files:
        cfg = _read_config_file(cfg_team_file)
        _validate_config_schema(file=cfg_team_file, cfg=cfg, schema=TEAM_CONFIG_SCHEMA)
        if overlap := set(cfg_teams.keys()) & set(cfg.keys()):
            logging.critical(
                "The config file '%s' contains keys that are also defined in "
                "other config files. This is disallowed. Affected keys: %s",
                cfg_team_file,
                ", ".join(overlap),
            )
            sys.exit(1)
        else:
            # Merge the dicts into one
            cfg_teams = cfg_teams | cfg

    return cfg_org, cfg_app, cfg_teams
