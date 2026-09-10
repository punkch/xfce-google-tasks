# GitHub releases and the apt repo — User guide

## How a release happens

1. Work on `development` with conventional commits (`feat:`, `fix:`).
2. Merge `development` into `main` and push.
3. release-please opens a PR "chore(main): release X.Y.Z". It bumps
   `gtasks_panel/__init__.py`, `version.txt` and `CHANGELOG.md`.
4. Merge that PR. The workflow makes the tag `vX.Y.Z` and the GitHub
   release, builds the deb, attaches it to the release, and publishes
   the apt repo to `gh-pages`.
5. A few minutes later `apt update` on a client shows the new version.

## Install from the apt repo

```
curl -fsSL https://punkch.github.io/xfce-google-tasks/gtasks-panel.gpg | sudo tee /usr/share/keyrings/gtasks-panel.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/gtasks-panel.gpg] https://punkch.github.io/xfce-google-tasks stable main" | sudo tee /etc/apt/sources.list.d/gtasks-panel.list
sudo apt update && sudo apt install gtasks-panel
```

## Build the deb locally

```
/usr/bin/make deb
```

If `gtasks_panel/__init__.py` has a newer version than the top of
`debian/changelog`, `make deb` adds a changelog entry first with `dch`.
Commit that entry if you want it in history.

## Rotate the signing key

1. `gpg --batch --quick-gen-key "gtasks-panel apt repo <you@example.com>" ed25519 sign never`
2. `gpg --armor --export-secret-keys <fingerprint> | gh secret set GPG_PRIVATE_KEY`
3. `gh variable set APT_SIGNING_KEY --body <fingerprint>`
4. Make a release. Clients must fetch the new `gtasks-panel.gpg`.

## Manual test table

| # | Step | Expected |
|---|------|----------|
| 1 | Push to `development`. | The "CI" workflow is green and has a deb artifact. |
| 2 | Merge to `main`, push. | release-please opens the release PR. |
| 3 | Merge the release PR. | Tag, release with the deb attached, `gh-pages` updated. |
| 4 | `curl -fsSL https://punkch.github.io/xfce-google-tasks/dists/stable/InRelease` | Starts with `-----BEGIN PGP SIGNED MESSAGE-----`. |
| 5 | On a client: the three install commands. | `apt-cache policy gtasks-panel` shows the new version from the Pages URL. |
| 6 | `sudo apt install gtasks-panel` | Installs. `gtasks-panel --version` prints the version. |
