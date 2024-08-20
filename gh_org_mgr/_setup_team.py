# SPDX-FileCopyrightText: 2024 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Functions to help with setting up new team"""

import logging
from os.path import isfile, join
from string import Template

from slugify import slugify

TEAM_TEMPLATE = """
${team_name}:
  # parent:
  # repos:
  # maintainer:
  member:
"""


def _sanitize_two_exclusive_options(option1: str | None, option2: str | None) -> bool:
    """Only of of these two options must be provided (not None, empty string is
    OK). Returns True if no error ocourred"""
    # There must not be a file_path and config_path provided at the same time
    if option1 is not None and option2 is not None:
        logging.critical("The two options must not be provided at the same time. Choose only one.")
        return False
    # There must at least be config_path or file_path configured
    if option1 is None and option2 is None:
        logging.critical("One of the two options must be provided")
        return False

    return True


def _fill_template(template: str, **fillers) -> str:
    """Fill a template using a dicts with keys and their values. The function
    looks for the keys starting with '$' characters"""
    return Template(template).substitute(fillers).lstrip()


def _ask_user_action(question: str, *options: str) -> str:
    """Ask the user a question and for an action. Return the chosen action."""
    option_dict: dict[str, str] = {}
    option_questions: list[str] = []
    for option in options:
        # Get first unique characters from the option
        short = ""
        i = 0
        while not short:
            i += 1
            short_try = option[:i]
            if short_try not in option_dict:
                short = short_try
                option_questions.append(option.replace(short, f"[{short}]", 1))
                option_dict[option] = option
                option_dict[short] = option

    response = ""
    while response not in option_dict:
        response = input(f"{question} ({'/'.join(option_questions)}): ")

    return option_dict[response]


def write_file(file: str, content: str, append: bool = False) -> None:
    """Write to a file. Overrides by default, but can also append"""
    mode = "a" if append else "w"
    try:
        with open(file, mode=mode, encoding="UTF-8") as writer:
            # Add linebreak if using append mode
            if mode == "a":
                writer.write("\n")

            # Add content to file
            writer.write(content)
    except FileNotFoundError as exc:
        logging.critical("File %s could not be written: %s", file, exc)


def setup_team(
    team_name: str, config_path: str | None = None, file_path: str | None = None
) -> None:
    """Set up a new team inside the config dir with a given name"""
    _sanitize_two_exclusive_options(config_path, file_path)

    # Come up with file name based on team name in the given config directory
    if not file_path:
        # Combine config dir and file name
        file_path = join(config_path, "teams", slugify(team_name) + ".yaml")  # type: ignore
        logging.debug("Derived file path: %s", file_path)

    # Fill template
    yaml_content = _fill_template(TEAM_TEMPLATE, team_name=team_name)

    # If file already exists, ask if file should be extended or overridden, or abort
    if isfile(file_path):
        options = ("override", "append", "print", "skip")
        action = _ask_user_action(
            f"The file {file_path} exists, what would you like to do?", *options
        )

        logging.debug("Chosen action: %s", action)

        if action == "skip":
            print("No action taken")
        elif action == "print":
            print()
            print(yaml_content)
        elif action in ("override", "append"):
            append = action == "append"
            write_file(file=file_path, content=yaml_content, append=append)

    # File does not exist, write file
    else:
        print(f"Writing team configuration into {file_path}")
        write_file(file=file_path, content=yaml_content)
