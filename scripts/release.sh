#!/bin/bash
set -e

read -p "Tag version (e.g. v1.2.0): " TAG
read -p "Release title: " TITLE

echo ""
echo "Creating release $TAG - $TITLE"
echo ""

# Create tag only if it doesn't already exist locally
if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "Tag $TAG already exists locally, reusing it."
else
    git tag "$TAG"
fi

git push origin "$TAG"
gh release create "$TAG" dist/SlaytheSpire2Drawing.exe --title "$TITLE" --generate-notes

echo ""
echo "Release published!"
