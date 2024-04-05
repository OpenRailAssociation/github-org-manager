"""Handling the private and organisation configuration"""

import yaml

# Global file with settings for the app, e.g. GitHub token
APP_CONFIG_FILE = "config/app_config.yaml"


def get_config(file: str, setting: str) -> str:
    """Get the value for a specific config"""
    with open(file, encoding="UTF-8") as yamlfile:
        config = yaml.safe_load(yamlfile)

    return config[setting]


def get_app_config(setting: str) -> str:
    """Get the app's config"""
    return get_config(APP_CONFIG_FILE, setting)
