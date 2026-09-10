#!/bin/bash
# Put a .deb into a static apt repo and sign the repo.
#
# Usage: publish-apt.sh <deb> <site dir>
#
# The site dir becomes the root of the apt repo. Serve it with GitHub
# Pages, or read it with a "file://" source line for a test.
#
# The environment variable APT_SIGNING_KEY holds the fingerprint of the
# secret key that signs the Release file.
set -euo pipefail

usage() {
    echo "usage: publish-apt.sh <deb> <site dir>" >&2
    exit 2
}

[ $# -eq 2 ] || usage
DEB=$1
SITE=$2
SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
CONF="$SCRIPT_DIR/apt-release.conf"

# The three install commands. The index page and the README show them.
PAGES_URL="https://punkch.github.io/xfce-google-tasks"
REPO_URL="https://github.com/punkch/xfce-google-tasks"

die() { echo "publish-apt.sh: $*" >&2; exit 1; }

[ -f "$DEB" ] || die "no such file: $DEB"
[ -f "$CONF" ] || die "no such file: $CONF"
command -v apt-ftparchive >/dev/null 2>&1 || die "apt-ftparchive is not installed (apt-utils)."
command -v gpg >/dev/null 2>&1 || die "gpg is not installed."

KEY=${APT_SIGNING_KEY:-}
[ -n "$KEY" ] || die "set APT_SIGNING_KEY to the fingerprint of the signing key."
gpg --list-secret-keys "$KEY" >/dev/null 2>&1 \
    || die "gpg has no secret key $KEY."

DEB_ABS=$(readlink -f "$DEB")
mkdir -p "$SITE"
SITE_ABS=$(readlink -f "$SITE")

mkdir -p "$SITE_ABS/pool/main" \
         "$SITE_ABS/dists/stable/main/binary-all" \
         "$SITE_ABS/dists/stable/main/binary-amd64" \
         "$SITE_ABS/dists/stable/main/binary-arm64"

cp -f "$DEB_ABS" "$SITE_ABS/pool/main/"

cd "$SITE_ABS"

# Run from the repo root, so "Filename:" starts with "pool/".
apt-ftparchive packages pool > dists/stable/main/binary-all/Packages
# The package is "Architecture: all". Give each client architecture the
# same index, or apt does not see the package.
cp -f dists/stable/main/binary-all/Packages dists/stable/main/binary-amd64/Packages
cp -f dists/stable/main/binary-all/Packages dists/stable/main/binary-arm64/Packages
for arch in all amd64 arm64; do
    gzip -9 -k -f "dists/stable/main/binary-$arch/Packages"
done

# Old signatures must go first. apt-ftparchive reads the directory and
# would put them into the new Release file.
rm -f dists/stable/Release dists/stable/Release.gpg dists/stable/InRelease
# Write to a temporary file. A direct ">" makes apt-ftparchive find the
# half-written Release and put its own hash into the list.
tmp=$(mktemp)
apt-ftparchive -c "$CONF" release dists/stable > "$tmp"
mv "$tmp" dists/stable/Release
chmod 644 dists/stable/Release

# Release.gpg is for old apt clients, InRelease for new ones.
gpg --batch --yes --local-user "$KEY" --armor --detach-sign \
    -o dists/stable/Release.gpg dists/stable/Release
gpg --batch --yes --local-user "$KEY" --clearsign \
    -o dists/stable/InRelease dists/stable/Release

# The public key for the "signed-by" option of the source line.
gpg --batch --yes --export "$KEY" > gtasks-panel.gpg

# GitHub Pages must not run Jekyll: it hides the "dists" tree.
touch .nojekyll

cat > index.html <<HTML
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>gtasks-panel apt repo</title>
<style>
body { font-family: sans-serif; max-width: 46em; margin: 3em auto; padding: 0 1em;
       line-height: 1.5; color: #222; background: #fff; }
pre { background: #f4f4f4; padding: 1em; overflow-x: auto; border-radius: 4px; }
</style>
</head>
<body>
<h1>gtasks-panel apt repo</h1>
<p>Google Tasks for the XFCE panel. To install the package, run these
three commands:</p>
<pre>curl -fsSL $PAGES_URL/gtasks-panel.gpg | sudo tee /usr/share/keyrings/gtasks-panel.gpg &gt;/dev/null
echo "deb [signed-by=/usr/share/keyrings/gtasks-panel.gpg] $PAGES_URL stable main" | sudo tee /etc/apt/sources.list.d/gtasks-panel.list
sudo apt update &amp;&amp; sudo apt install gtasks-panel</pre>
<p>Source code, releases and the bug tracker:
<a href="$REPO_URL">$REPO_URL</a></p>
</body>
</html>
HTML

echo "Wrote:"
echo "  $SITE_ABS/pool/main/$(basename "$DEB_ABS")"
for arch in all amd64 arm64; do
    echo "  $SITE_ABS/dists/stable/main/binary-$arch/Packages"
    echo "  $SITE_ABS/dists/stable/main/binary-$arch/Packages.gz"
done
echo "  $SITE_ABS/dists/stable/Release"
echo "  $SITE_ABS/dists/stable/Release.gpg"
echo "  $SITE_ABS/dists/stable/InRelease"
echo "  $SITE_ABS/gtasks-panel.gpg"
echo "  $SITE_ABS/.nojekyll"
echo "  $SITE_ABS/index.html"
