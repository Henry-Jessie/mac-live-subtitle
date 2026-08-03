#!/bin/zsh

set -euo pipefail

script_dir=${0:A:h}
repo_root=${script_dir:h}

if [[ $# -ne 1 ]]; then
    print -u2 "Usage: $0 <version>"
    exit 2
fi

version=$1
if [[ ! "$version" =~ '^[0-9]+\.[0-9]+\.[0-9]+$' ]]; then
    print -u2 "Version must use MAJOR.MINOR.PATCH format"
    exit 2
fi

if [[ ! -f "$repo_root/setup.py" || ! -f "$repo_root/pyproject.toml" ]]; then
    print -u2 "Cannot locate the project root"
    exit 1
fi

cd "$repo_root"

signing_identity=${CODESIGN_IDENTITY:-Mac Live Subtitle Local Signing}
app_name="Mac Live Subtitle.app"
app_path="$repo_root/dist/$app_name"
release_dir="$repo_root/release/v$version"
archive_name="Mac-Live-Subtitle-v$version-macos-arm64.zip"
archive_path="$release_dir/$archive_name"
checksum_path="$release_dir/SHA256SUMS.txt"

available_identities=$(
    security find-identity -v -p codesigning
)
if [[ "$available_identities" != *"\"$signing_identity\""* ]]; then
    print -u2 "Code-signing identity not found: $signing_identity"
    exit 1
fi

rm -rf "$repo_root/build" "$repo_root/dist"
mkdir -p "$release_dir"
rm -f "$archive_path" "$checksum_path"

uv sync --group build --frozen
uv run python setup.py py2app

portaudio_path=$(
    find "$app_path/Contents/Resources/lib" \
        -path '*/_sounddevice_data/portaudio-binaries/libportaudio.dylib' \
        -type f \
        -print \
        -quit
)
if [[ -z "$portaudio_path" ]]; then
    print -u2 "Bundled PortAudio library not found"
    exit 1
fi

codesign \
    --force \
    --deep \
    --sign "$signing_identity" \
    --timestamp=none \
    "$app_path"
codesign --verify --deep --strict --verbose=2 "$app_path"

bundle_version=$(
    plutil -extract CFBundleShortVersionString raw \
        "$app_path/Contents/Info.plist"
)
if [[ "$bundle_version" != "$version" ]]; then
    print -u2 \
        "Bundle version $bundle_version does not match release $version"
    exit 1
fi

architectures=$(
    lipo -archs "$app_path/Contents/MacOS/Mac Live Subtitle"
)
if [[ "$architectures" != "arm64" ]]; then
    print -u2 "Expected arm64 bundle, found: $architectures"
    exit 1
fi

ditto -c -k --sequesterRsrc --keepParent \
    "$app_path" \
    "$archive_path"

(
    cd "$release_dir"
    shasum -a 256 "$archive_name" > "$checksum_path"
)

verification_dir=$(
    mktemp -d /tmp/mac-live-subtitle-release-verification.XXXXXX
)
trap 'rm -rf "$verification_dir"' EXIT

ditto -x -k "$archive_path" "$verification_dir"
codesign --verify --deep --strict --verbose=2 \
    "$verification_dir/$app_name"

extracted_version=$(
    plutil -extract CFBundleShortVersionString raw \
        "$verification_dir/$app_name/Contents/Info.plist"
)
if [[ "$extracted_version" != "$version" ]]; then
    print -u2 \
        "Extracted bundle version $extracted_version does not match $version"
    exit 1
fi

print "Release package verified:"
print "  $archive_path"
print "  $checksum_path"
