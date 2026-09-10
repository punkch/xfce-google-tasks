# GitHub releases and apt repo on GitHub Pages — Shaping Notes

## Scope

- A public GitHub repo `punkch/xfce-google-tasks`.
- release-please makes the release PR and the tag on `main`.
- The same workflow builds the deb, attaches it to the GitHub release,
  and publishes a signed apt repo to the `gh-pages` branch.
- Users install with one `sources.list` line.

## User answers (2026-09-10)

- "Option 1: GitHub Pages as the apt repo" with release-please,
  dpkg-buildpackage, apt-ftparchive and a GPG key in a repo secret.
- Repo: public `punkch/xfce-google-tasks`.
- GPG key: make a new dedicated key on this machine.
- release-please watches `main`.

## Decisions

- Build and publish run in the release-please workflow, in a job gated
  on `release_created`. A release made with `GITHUB_TOKEN` does not
  start an `on: release` workflow, and a personal access token is more
  to manage.
- `gtasks_panel/__init__.py` is the one version source. `make deb` adds
  a `debian/changelog` entry with `dch` when the top entry is older.
- The signing key has no passphrase. It signs this repo only. One
  secret (`GPG_PRIVATE_KEY`) and one variable (`APT_SIGNING_KEY`, the
  fingerprint).
- `apt-ftparchive`, not `reprepro`: no database, one package.
- The same `Packages` file goes under `binary-amd64`, `binary-arm64` and
  `binary-all`, because apt reads the directory of the host
  architecture.

## Out of scope

Signing the `.deb` itself, a source repo, more suites, `Contents`
index.

## Context

- **Visuals:** None.
- **References:** see `references.md`.
- **Product alignment:** N/A.

## Skills & Conventions Applied

- Global user rules: ASD-STE100, conventional commits after
  confirmation, no attribution trailers, keep `CLAUDE.md` current.
- Delivery workflow: one opus agent for the files, code-review skill
  with five agents, live verification in the main thread.

## As built (2026-09-10)

- `ci.yml` has two jobs: `build` (make deb, GTK smoke tests under xvfb,
  lintian, artifact) and `apt-repo` (runs `scripts/publish-apt.sh` with a
  throwaway key and checks the result with `apt-get update` against a
  `file://` source).
- `release.yml` runs lintian before it attaches the deb.
- `bump-patch-for-minor-pre-major` is off: a `feat` bumps the minor
  below 1.0 too, so the first release is 0.3.0.
- `make changelog` stops when it cannot read `debian/changelog`.
