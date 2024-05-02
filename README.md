<!--
SPDX-FileCopyrightText: 2024 DB Systel GmbH

SPDX-License-Identifier: Apache-2.0
-->

# GitHub Organization Manager

[![Test suites](https://github.com/OpenRailAssociation/github-org-manager/actions/workflows/test.yaml/badge.svg)](https://github.com/OpenRailAssociation/github-org-manager/actions/workflows/test.yaml)
[![REUSE status](https://api.reuse.software/badge/github.com/OpenRailAssociation/github-org-manager)](https://api.reuse.software/info/github.com/OpenRailAssociation/github-org-manager)
[![The latest version of GitHub Org Manager can be found on PyPI.](https://img.shields.io/pypi/v/github-org-manager.svg)](https://pypi.org/project/github-org-manager/)
[![Information on what versions of Python GitHub Org Manager supports can be found on PyPI.](https://img.shields.io/pypi/pyversions/github-org-manager.svg)](https://pypi.org/project/github-org-manager/)

A lightweight tool that helps with managing a GitHub organization, its members, teams, repository permissions and more.

The basic principle: all settings reside in YAML configuration files which will be made effective during a run of this tool.

## Features

* Manage GitHub teams and their members and maintainers
* Support of sub-teams
* Manage teams' permissions on organizations' repositories
* Invite members to the organization if they aren't part of it yet
* Warn about unmanaged teams
* Warn about organization members who are not part of any team

Are you missing a feature? Please check whether it's [already posted as an issue](https://github.com/OpenRailAssociation/github-org-manager/issues), and create one of this isn't the case.

## Install

Dependencies: Python 3.10 or newer

To install: `pip3 install github-org-manager`

You may also want to consider using helpers such as [`pipx`](https://pipx.pypa.io/) to avoid a dependency mess on your system.

Afterwards, the tool is executable with the command `gh-org-mgr`. The `--help` flag informs you about the required and available commands.

## Configuration

Inside [`config/example`](./config/example), you can find an example configuration that shall help you to understand the structure:

* `app.yaml`: Configuration necessary to run this tool
* `org.yaml`: Organization-wide configuration
* `teams/*.yaml`: Configuration concerning the teams of your organization.

You may also be interested in the [live configuration of the OpenRail Association's organization](https://github.com/OpenRailAssociation/openrail-org-config).

## Run the program

You can execute the program using the command `gh-org-mgr`. `gh-org-mgr --help` shows all available arguments and options.

Some examples:

* `gh-org-mgr -c myorgconf`: synchronize the settings of the GitHub organization with your local configuration in the given configuration path (`myorgconf`). This may create new teams, remove/add members, and change permissions.
* `gh-org-mgr -c myorgconf --dry`: as above, but do not make any modification. Perfect for testing your local configuration and see its potential effects.
* `gh-org-mgr -c myorgconf --debug`: the first example, but show full debugging information.

## License

The content of this repository is licensed under the [Apache 2.0 license](https://www.apache.org/licenses/LICENSE-2.0).

There may be components under different, but compatible licenses or from different copyright holders. The project is REUSE compliant which makes these portions transparent. You will find all used licenses in the [LICENSES](./LICENSES/) directory.

The project is has been started by the [OpenRail Association](https://openrailassociation.org). You are welcome to [contribute](./CONTRIBUTING.md)!
