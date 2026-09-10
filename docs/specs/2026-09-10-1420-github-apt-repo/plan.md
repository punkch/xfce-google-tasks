# gtasks-panel: GitHub repo, release-please, deb build and an apt repo on GitHub Pages

## Context

The package lives only on this machine. The user wants releases on GitHub and an apt repo
that users add with one `sources.list` line. Chosen: GitHub Pages serves the static apt repo,
release-please makes the release PR and the tag, a workflow builds the deb and publishes it.

User answers (2026-09-10): public repo `punkch/xfce-google-tasks`; a new dedicated GPG key
made here and stored as a repository secret; release-please watches `main`.

## Facts verified

- No git remote and no `main` branch yet. `gh` is logged in as `punkch`. Local tools:
  `apt-ftparchive`, `gpg`, `dch`, `lintian` present; `reprepro` and `act` absent.
- release-please: `extra-files` with the generic updater replaces the version on a line that
  carries `x-release-please-version`; release type `simple` updates `version.txt` and
  `CHANGELOG.md`; manifest mode uses `release-please-config.json` and
  `.release-please-manifest.json`. Action v4 outputs `release_created`, `tag_name`,
  `version`. A release made with the default `GITHUB_TOKEN` does **not** start another
  workflow (`on: release`). So the build and the publish run in the same workflow, in a job
  that waits for the release-please job and runs only when `release_created` is true. No
  personal access token. (Sources: googleapis/release-please docs/customizing.md and the
  release-please-action README, fetched 2026-09-10.)
- `Makefile` reads `VERSION` from `dpkg-parsechangelog`. `debian/changelog` and
  `gtasks_panel/__init__.py` are both bumped by hand today.
- The package is `Architecture: all`. apt clients fetch `binary-<hostarch>/Packages`, so the
  same `Packages` file goes under `binary-amd64`, `binary-arm64` and `binary-all`.

## Design decisions

1. **Version source.** `gtasks_panel/__init__.py` (`VERSION = "x.y.z"  # x-release-please-version`)
   is the one source. release-please also keeps `version.txt` (its own file) and writes
   `CHANGELOG.md`. `debian/changelog` becomes history: a new Makefile target `changelog`
   runs `dch --newversion $(PKG_VERSION) --distribution unstable --controlmaint
   "Release $(PKG_VERSION). See CHANGELOG.md."` only when the top entry is older than the
   package version. `deb` depends on `changelog`. `PKG_VERSION` is read from
   `gtasks_panel/__init__.py` with a `sed`. The CLAUDE.md version convention line changes.
2. **release-please.** `release-please-config.json`: `release-type: simple`,
   `include-component-in-tag: false` (tags `v0.3.0`), `extra-files:
   ["gtasks_panel/__init__.py"]`, `changelog-sections` for feat/fix/perf/refactor/docs.
   `.release-please-manifest.json`: `{".": "0.2.0"}`. Setup pushes tag `v0.2.0` on `bfd6792`
   so the first release PR proposes 0.3.0 from the commits after it.
3. **Workflows.**
   - `.github/workflows/ci.yml`: on push and pull_request to `main` and `development`:
     `apt-get install debhelper devscripts python3-pytest python3-gi gir1.2-gtk-3.0
     desktop-file-utils lintian`, `make check`, `make deb`, `lintian dist/*.deb`, upload the
     deb as a workflow artifact.
   - `.github/workflows/release.yml`: on push to `main`. Job `release` runs
     `googleapis/release-please-action@v4` (config and manifest files). Job `publish`
     (`needs: release`, `if: needs.release.outputs.release_created == 'true'`,
     `permissions: contents: write`): checkout the tag, install the build tools, `make deb`
     (the `changelog` target adds the entry for this version), `gh release upload
     $TAG dist/*.deb`, then run `scripts/publish-apt.sh dist/*.deb site` and push `site` to
     `gh-pages`.
4. **`scripts/publish-apt.sh`** (bash, `set -euo pipefail`, runs locally too): arguments
   `<deb> <site dir>`. Steps: copy the deb to `site/pool/main/`; `apt-ftparchive packages
   pool > dists/stable/main/binary-all/Packages` (run from `site`, so `Filename:` is
   `pool/main/...`); copy that `Packages` to `binary-amd64` and `binary-arm64`; `gzip -9 -k
   -f` each; `apt-ftparchive -c scripts/apt-release.conf release dists/stable >
   dists/stable/Release` (conf: `Origin`, `Label`, `Suite stable`, `Codename stable`,
   `Architectures amd64 arm64 all`, `Components main`, `Description`); `gpg --batch --yes
   --armor --detach-sign -o Release.gpg Release` and `gpg --batch --yes --clearsign -o
   InRelease Release`; `gpg --export <key id> > site/gtasks-panel.gpg`; touch
   `site/.nojekyll`; write `site/index.html` with the three install commands. The key id
   comes from `$APT_SIGNING_KEY` (fingerprint) so the script never guesses a key.
5. **GPG key.** Setup makes a key with no passphrase: `gpg --batch --quick-gen-key
   "gtasks-panel apt repo <pencho@belneiski.com>" ed25519 sign never`. No passphrase: the
   key exists only to sign this repo, and one secret is simpler than two. The private key
   goes to the repo secret `GPG_PRIVATE_KEY` (`gpg --armor --export-secret-keys`), the
   fingerprint to the repository variable `APT_SIGNING_KEY`. The user keeps the key in
   `~/.gnupg`. The workflow imports the key with `gpg --batch --import`.
6. **Client line** (README, `index.html`, `CLAUDE.md`):
   ```
   curl -fsSL https://punkch.github.io/xfce-google-tasks/gtasks-panel.gpg | sudo tee /usr/share/keyrings/gtasks-panel.gpg >/dev/null
   echo "deb [signed-by=/usr/share/keyrings/gtasks-panel.gpg] https://punkch.github.io/xfce-google-tasks stable main" | sudo tee /etc/apt/sources.list.d/gtasks-panel.list
   sudo apt update && sudo apt install gtasks-panel
   ```
7. **Setup steps done by me in the main thread, after plan approval** (they reach an
   audience): `gh repo create punkch/xfce-google-tasks --public --source . --remote origin`;
   create `main` from `development`; push both branches and tag `v0.2.0`; create an empty
   `gh-pages` branch (`.nojekyll` only) and push it; enable Pages from `gh-pages` root with
   `gh api`; make the GPG key; `gh secret set GPG_PRIVATE_KEY`; `gh variable set
   APT_SIGNING_KEY`. Pushes of the CI commit and later merges are part of this approval.
8. **Not in scope:** signing the `.deb` itself (`debsigs`), a `source` repo, multiple
   suites, apt `Contents` index, arm64 builds (the package is `all`, the arch dirs only
   point apt at it).

## Tasks

### Task 1: Spec documentation (main thread)

`docs/specs/2026-09-10-1420-github-apt-repo/` with `plan.md` (this plan), `shape.md`,
`standards.md`, `references.md` (Makefile `deb` target, `debian/rules`, release-please docs),
`user-guide.md` (how a release happens, how to install from the repo, how to rotate the key).

### Task 2: Files (Agent 1, opus, after the 0.3.0 workflow's UI agent is done)

Owns: `.github/workflows/ci.yml`, `.github/workflows/release.yml`,
`release-please-config.json`, `.release-please-manifest.json`, `version.txt`,
`scripts/publish-apt.sh`, `scripts/apt-release.conf`, `Makefile` (`changelog` target,
`PKG_VERSION`, `deb` dependency), `gtasks_panel/__init__.py` (add the annotation comment
only), `.gitignore` (`site/`), `README.md` (an "Install from the apt repo" section and a
"Releases" section) and `CLAUDE.md` (layout rows, version convention, facts). Decisions 1–4
and 6. Local checks the agent runs: `bash -n`, `shellcheck` if present, `make check`,
`make changelog` on a scratch copy proves it adds an entry only when the version lags,
`scripts/publish-apt.sh` with a throwaway GPG key into a scratch `site/`, then
`apt-get update` against it with a scratch apt config (`-o Dir::Etc::sourcelist=...
-o Dir::State=... -o Dir::Cache=... -o Dir::Etc::trusted=...` and a
`deb [signed-by=...] file:///scratch/site stable main` line) and `apt-cache policy
gtasks-panel` shows the version. Also validate the YAML with `python3 -c "import yaml"` if
`python3-yaml` is present, else `gh workflow view` after the push.

### Task 3: Setup and live verification (main thread)

Decision 7, then: push the CI commit to `development`, watch `gh run watch` for `ci.yml`;
merge `development` into `main` and push; watch `release.yml`: the release PR appears;
merge the release PR (`gh pr merge --squash`); watch the publish job; check
`https://punkch.github.io/xfce-google-tasks/dists/stable/InRelease` with `curl`; on this
machine add the source line and run `apt update` and `apt-cache policy gtasks-panel`;
install from the repo; `gtasks-window --quit` and click the panel.

### Task 4: Review (main thread)

`/unops-toolkit:code-review` with its five agents on the diff. Apply findings. Final
`advisor` call.

## Workflow and agent setup

| Agent | Model | Owns | Runs |
|-------|-------|------|------|
| 1 files | opus | `.github/`, release-please files, `scripts/`, `Makefile`, `README.md`, `CLAUDE.md`, `.gitignore`, the annotation line in `__init__.py` | after the 0.3.0 docs agent is done (README overlap) |
| review | code-review skill, 5 agents | read-only | after Task 3 |

One agent, no parallel edits. Setup, pushes and the live check are the session model in the
main thread. Total: 1 agent + 5 review agents.

## Commits (conventional, no attribution trailer)

1. `feat: GTK window replaces Chrome (gtasks-panel 0.2.0)` exists (`bfd6792`); tag `v0.2.0`.
2. The 0.3.0 commit (separate approval, after its own verification).
3. `ci: release-please, deb build and apt repo on GitHub Pages`.

## Verification

- Local: the scratch apt repo test in Task 2 (apt accepts the signature and lists the
  package).
- Remote: `ci.yml` green on `development`; the release PR; the publish job green; the
  `InRelease` file served by Pages; `apt update` + `apt install gtasks-panel` on this
  machine from the real repo.

## Risks

- GitHub Pages takes up to a few minutes after the push to serve new files. The live check
  waits and retries `curl`.
- The first release PR needs the tag `v0.2.0` to exist, else release-please reads the whole
  history. Setup pushes the tag before the first push to `main`.
- `dch` in CI needs `devscripts` (big, about 1 minute of apt time). Accepted.
