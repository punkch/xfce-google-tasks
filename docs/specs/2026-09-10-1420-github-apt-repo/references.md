# References for the GitHub apt repo

## Makefile `deb` target

- **Location:** `Makefile`, targets `check`, `deb`, `clean`; `VERSION`
  from `dpkg-parsechangelog -S Version`.
- **Relevance:** the new `changelog` target runs before `deb`, and
  `PKG_VERSION` comes from `gtasks_panel/__init__.py`.

## Debian rules

- **Location:** `debian/rules` (`dh $@`, `make install PREFIX=/usr`),
  `debian/control` (Build-Depends: debhelper-compat 13, python3,
  python3-pytest).
- **Relevance:** the CI job installs exactly these plus `devscripts`
  (for `dch`), `apt-utils` (for `apt-ftparchive`), `lintian`,
  `desktop-file-utils`, `python3-gi` and `gir1.2-gtk-3.0` (the store,
  worker and click tests import `gi`).

## release-please

- **Docs:** `docs/customizing.md` in googleapis/release-please:
  `extra-files`, generic updater, annotation `x-release-please-version`;
  release type `simple` (`version.txt`, `CHANGELOG.md`).
- **Action:** googleapis/release-please-action v4 README: inputs
  `config-file`, `manifest-file`, `target-branch`; outputs
  `release_created`, `tag_name`, `version`; the note that
  `GITHUB_TOKEN` events start no other workflow.

## apt-ftparchive

- `man apt-ftparchive` on the dev host (apt-utils 3.x). Commands
  `packages`, `release`, config `APT::FTPArchive::Release::*`.

## Version string sites

- `gtasks_panel/__init__.py` (VERSION), `debian/changelog` (top entry),
  `README.md`, `CLAUDE.md`, `man/*.1` (`.TH` line), `debian/control`
  (no version).
