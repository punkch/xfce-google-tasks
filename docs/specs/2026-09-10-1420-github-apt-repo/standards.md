# Skills & Conventions for the GitHub apt repo

## Project conventions (`CLAUDE.md`)

- Docs and chat in ASD-STE100 Simplified Technical English.
- Conventional commits. Commit only after the user confirms. No
  attribution trailer. release-please reads the commit types: `feat`
  bumps minor, `fix` bumps patch, `feat!` or `BREAKING CHANGE` bumps
  major.
- Version source: `gtasks_panel/__init__.py` with the
  `x-release-please-version` annotation. `debian/changelog` is history.
- Update `CLAUDE.md` in the same change when layout or conventions
  change.

## Debian packaging

- debhelper 13, native source format, `Architecture: all`.
- `dpkg-buildpackage -us -uc -b` builds the binary package. `-us -uc`
  skips source and changes signing. The apt `Release` file is signed
  instead.
- lintian must stay clean.

## apt repo layout

```
site/
  .nojekyll
  index.html
  gtasks-panel.gpg                 binary public key (for signed-by)
  pool/main/gtasks-panel_X_all.deb
  dists/stable/
    Release, Release.gpg, InRelease
    main/binary-all/Packages, Packages.gz
    main/binary-amd64/Packages, Packages.gz
    main/binary-arm64/Packages, Packages.gz
```

- `apt-ftparchive packages pool` runs from `site/`, so `Filename:` is
  relative to the repo root.
- `apt-ftparchive release dists/stable` needs a conf with `Origin`,
  `Label`, `Suite`, `Codename`, `Architectures`, `Components`,
  `Description`.
- `InRelease` (clearsigned) is what modern apt reads first;
  `Release.gpg` is the detached signature for older apt.

## GitHub Actions

- `permissions: contents: write` on the publish job (release upload and
  the `gh-pages` push). `pull-requests: write` and `contents: write` on
  the release-please job.
- Secrets: `GPG_PRIVATE_KEY`. Variables: `APT_SIGNING_KEY`.
- Never print the private key. `gpg --batch --import` reads it from
  stdin.
