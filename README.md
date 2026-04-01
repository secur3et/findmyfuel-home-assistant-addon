# Find My Fuel Home Assistant Add-on Repository

This directory is the clean standalone repository you can publish to GitHub for Home Assistant users.

It contains:

- `repository.yaml` for the add-on repository metadata
- `findmyfuel/` as the installable Home Assistant add-on

The add-on is self-contained. It includes its own Python application source under `findmyfuel/app/` and does not depend on files outside this repository.

## Repository Layout

```text
findmyfuel-addon-repo/
  repository.yaml
  findmyfuel/
    config.yaml
    Dockerfile
    run.sh
    DOCS.md
    README.md
    icon.png
    logo.png
    translations/en.yaml
    app/
      pyproject.toml
      README.md
      src/findmyfuel/...
```

## Publish

Create a new public GitHub repository and publish the contents of this folder as the repository root.

After the repo exists, update:

- `repository.yaml`
- `findmyfuel/config.yaml`

so their `url` fields point at the real GitHub repository URL.
