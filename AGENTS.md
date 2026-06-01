# AGENTS.md

This repository uses shared setup guidance for human teammates and AI coding agents.

Read this first:

- [docs/setup-guide.md](docs/setup-guide.md)

Useful companion docs:

- [README.md](README.md)

Key rules for agents:

- Keep the project uv-based. Do not add requirements files.
- Keep the current root package layout: `config/`, `apps/`, `common/`, `infrastructure/`.
- Use `config.settings.*` for Django settings.
- Put new Django apps under `apps/`.
- Update docs when changing project structure, setup, CI, or runtime behavior.
