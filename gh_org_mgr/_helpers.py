# SPDX-FileCopyrightText: 2025 DB Systel GmbH
#
# SPDX-License-Identifier: Apache-2.0

"""Helper functions"""

import logging
import sys
from dataclasses import asdict


def configure_logger(verbose: bool = False, debug: bool = False) -> logging.Logger:
    """Set logging options"""
    log = logging.getLogger()
    logging.basicConfig(
        encoding="utf-8",
        format="[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    if debug:
        log.setLevel(logging.DEBUG)
    elif verbose:
        log.setLevel(logging.INFO)
    else:
        log.setLevel(logging.WARNING)

    return log


def log_progress(message: str) -> None:
    """Log progress messages to stderr"""
    # Clear line if no message is given
    if not message:
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()
    else:
        sys.stderr.write(f"\r\033[K⏳ {message}")
        sys.stderr.flush()


def sluggify_teamname(team: str) -> str:
    """Slugify a GitHub team name"""
    # TODO: this is very naive, no other special chars are
    # supported, or multiple spaces etc.
    return team.replace(" ", "-")


def compare_two_lists(list1: list[str], list2: list[str]):
    """
    Compares two lists of strings and returns a tuple containing elements
    missing in each list and common elements.

    Args:
        list1 (list of str): The first list of strings.
        list2 (list of str): The second list of strings.

    Returns:
        tuple: A tuple containing three lists:
            1. The first list contains elements in `list2` that are missing in `list1`.
            2. The second list contains elements that are present in both `list1` and `list2`.
            3. The third list contains elements in `list1` that are missing in `list2`.

    Example:
        >>> list1 = ["apple", "banana", "cherry"]
        >>> list2 = ["banana", "cherry", "date", "fig"]
        >>> compare_lists(list1, list2)
        (['date', 'fig'], ['banana', 'cherry'], ['apple'])
    """
    # Convert lists to sets for easier comparison
    set1, set2 = set(list1), set(list2)

    # Elements in list2 that are missing in list1
    missing_in_list1 = list(set2 - set1)

    # Elements present in both lists
    common_elements = list(set1 & set2)

    # Elements in list1 that are missing in list2
    missing_in_list2 = list(set1 - set2)

    # Return the result as a tuple
    return (missing_in_list1, common_elements, missing_in_list2)


def compare_two_dicts(dict1: dict, dict2: dict) -> dict[str, dict[str, str | int | None]]:
    """Compares two dictionaries. Assume that the keys are the same. Output
    a dict with keys that have differing values"""
    # Create an empty dictionary to store differences
    differences = {}

    # Iterate through the keys (assuming both dictionaries have the same keys)
    for key in dict1:
        # Compare the values for each key
        if dict1[key] != dict2[key]:
            differences[key] = {"dict1": dict1[key], "dict2": dict2[key]}

    return differences


def dict_to_pretty_string(dictionary: dict, sensible_keys: None | list[str] = None) -> str:
    """Convert a dict to a pretty-printed output"""

    # Censor sensible fields
    def censor_half_string(string: str) -> str:
        """Censor 50% of a string (rounded up)"""
        half1 = int(len(string) / 2)
        half2 = len(string) - half1
        return string[:half1] + "*" * (half2)

    if sensible_keys is None:
        sensible_keys = []
    for key in sensible_keys:
        if value := dictionary.get(key, ""):
            dictionary[key] = censor_half_string(value)

    # Print dict nicely
    def pretty(d, indent=0):
        string = ""
        for key, value in d.items():
            string += "  " * indent + str(key) + ":\n"
            if isinstance(value, dict):
                string += pretty(value, indent + 1)
            else:
                string += "  " * (indent + 1) + str(value) + "\n"

        return string

    return pretty(dictionary)


def pretty_print_dataclass(dc):
    """Convert dataclass to a pretty-printed output"""
    dict_to_pretty_string(asdict(dc))


def implement_changes_into_class(dc_object, **changes: bool | str | list[str]):
    """Smartly add changes to a (data)class object"""
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
