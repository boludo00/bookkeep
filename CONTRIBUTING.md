# Contributing

## Branching

- Branch from `develop` for feature work.
- Open PRs into `develop`.
- For releases, open a PR from `develop` to `main` and add one label:
  - `bump:major`
  - `bump:minor`
  - `bump:patch`

## Releases

Merging the `develop` → `main` PR triggers:

- A new git tag like `vX.Y.Z`
- Docker Hub publish for `bookkeep/bookkeep`

## Labels

Create these labels in GitHub:

- `bump:major`
- `bump:minor`
- `bump:patch`
