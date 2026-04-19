<!--
SPDX-FileCopyrightText: 2024 GitHub, Inc.
SPDX-FileCopyrightText: 2024 DB Systel GmbH

SPDX-License-Identifier: CC-BY-4.0
-->

# Contributing

This Project welcomes contributions, suggestions, and feedback. All contributions, suggestions, and feedback you submitted are accepted under the [Project's license](./LICENSE.txt). You represent that if you do not own copyright in the code that you have the authority to submit it under the [Project's license](./LICENSE.txt). All feedback, suggestions, or contributions are not confidential.

## Development setup

Starting development is as easy as installing [uv](https://docs.astral.sh/uv/) and running `uv sync` once.

In order to run the project in the new virtual environment, run `uv run gh-org-mgr`.

## Commit Messages

This project follows the [**Conventional Commits**](https://www.conventionalcommits.org/) specification for commit messages. This is critical to support proper automation of the release process and changelog generation.

## Pull Requests

When contributing to this project, please open a pull request with a clear description of the changes you have made. The **title of your pull request** should follow the conventional commit format (e.g., `feat: add new feature`, `fix: correct a bug`, etc.).

Ensure to use the **Squash and merge** option when merging your pull request.

Both the PR title and merge method are required for a proper release process (see below).

## Release Process

This project uses [release-please](https://github.com/googleapis/release-please) and its respective GitHub Action to automate the release process. This automatically creates a pull request with the version bump and changelog updates whenever a commit is pushed to the default branch. The version bump is determined by the [conventional commit messages](https://www.conventionalcommits.org/) in the commit history since the last release. Once the release pull request is merged, a new release will be published on GitHub.

The relevant configuration for release-please can be found in the `.github/workflows/release-please.yaml` file and the `release-please-config.json` file. Ensure that the branch and project names are correctly set up in the workflow file and configuration file to match your repository's structure.

---
Based on [GitHub's Minimum Viable Governance (MVG)](https://github.com/github/MVG). Licensed under the [CC-BY 4.0 License](https://creativecommons.org/licenses/by/4.0/).
