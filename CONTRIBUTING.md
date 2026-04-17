# Contributing to LogstashUI

Thanks for your interest in contributing to LogstashUI!

LogstashUI is still evolving, and the contributor experience is lightweight in some areas while the project continues to mature. If something is unclear, feel free to open an issue or discussion before starting work.

## Scope

LogstashUI is focused specifically on Logstash.

The goal of the project is to provide a control plane, monitoring experience, and pipeline authoring workflow for Logstash. Contributions should stay closely aligned with improving how users build, manage, inspect, validate, and operate Logstash.

Ideas that fall outside that scope may still be useful, but are unlikely to be accepted here. This includes features that turn LogstashUI into a general-purpose observability console, network utility toolkit, or multi-platform ingestion management interface.

Examples of likely out-of-scope contributions include:

- Features centered on technologies other than Logstash
- General network or systems utilities such as ping, traceroute, or similar tools
- Broader control-plane features not directly related to managing Logstash
- Expanding existing areas in ways that move them away from Logstash-focused workflows

If you're unsure whether an idea fits the project, please open an issue or discussion before investing significant time in implementation.


## Ways to contribute

There are several ways to contribute to LogstashUI:

- Report bugs
- Suggest features or UX improvements
- Improve documentation
- Fix bugs or implement enhancements
- Share feedback from real-world usage

## Before you start

For larger changes, please open an issue or start a discussion first so we can align on scope and direction before significant work begins.

This helps avoid duplicate effort and makes it easier to keep contributions aligned with the project's goals and roadmap.

## Development setup

See the [build](/docs/docs/logstashui/general/build.md) document for setup instructions.

Example:

1. Fork the repository
2. Clone your fork
3. Create a branch for your change
4. Follow the setup instructions in the README or build document
5. Run the application locally and verify your changes


## Coding expectations

A few general guidelines:

- Keep changes focused and scoped
- Prefer consistency with the existing codebase over unnecessary abstraction
- Avoid unrelated refactors in feature or bugfix pull requests
- Update documentation when behavior or workflows change
- Test your changes manually before opening a pull request


## Pull requests

When opening a pull request:

- Clearly describe the problem being solved
- Include screenshots or recordings for UI changes when possible
- Note any known limitations or follow-up work
- Keep pull requests reasonably focused and reviewable

Small, focused pull requests are preferred over large unrelated bundles of changes.

## Reporting bugs

When reporting a bug, please use [this template](https://github.com/elastic/LogstashUI/issues/new?template=issue.md), and be sure to include:

- What you expected to happen
- What actually happened
- Steps to reproduce the issue
- Screenshots, logs, or error messages if available
- Environment details when relevant

## Feature requests

Feature requests are welcome, especially when they are tied to a clear user problem or workflow.

If possible, explain:

- the use case,
- the current limitation,
- and what a better experience would look like.

## Questions and discussion

If you're unsure whether a change is a good fit, open an issue or discussion first.

## Project maturity

LogstashUI is an actively evolving project, and some tooling, workflows, and contribution conventions may change over time. Contributions are still very welcome, even while parts of the project are becoming more formalized.