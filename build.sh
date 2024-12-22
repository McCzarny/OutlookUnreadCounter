#!/bin/bash

# Increment the version number in the plugin's manifest.json file and run the build process
MANIFEST_FILE="./com.mcczarny.outlookunreadcounter.sdPlugin/manifest.json"
VERSION_NUMBER=$(grep -oP '"Version": "\K[^"]*' $MANIFEST_FILE)
echo "Current version number: $VERSION_NUMBER"
echo "Incrementing version number..."
# Increment the version number
NEW_VERSION_NUMBER=$(echo $VERSION_NUMBER | awk -F. '{$NF = $NF + 1;} 1' | sed 's/ /./g')
echo "New version number: $NEW_VERSION_NUMBER"
# Replace the version number in the manifest.json file
sed -i "s/$VERSION_NUMBER/$NEW_VERSION_NUMBER/g" $MANIFEST_FILE

# Run the build process
SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )

"${SCRIPT_DIR}/.venv/Scripts/streamdeck_sdk.exe" build -i com.mcczarny.outlookunreadcounter.sdPlugin
