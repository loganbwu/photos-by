#!/bin/bash
# This script ensures the environment is synced and dependencies are exported
# before deploying to Google Cloud. It's meant to be run from within the 'backend' directory.

# Exit immediately if a command exits with a non-zero status.
set -e

echo "Step 1: Syncing Rye environment to ensure pip is installed..."
rye sync
echo "Environment is up to date."

echo ""
echo "Step 2: Exporting dependencies to requirements.txt..."
# Use `rye list` to generate the requirements file.
# The `grep -v '^-e'` is crucial to remove the local, editable project path,
# which is not a valid dependency for Google Cloud.
rye list | grep -v '^-e' > requirements.txt
echo "Successfully created requirements.txt."

echo ""
echo "Step 3: Deploying to Google Cloud Functions..."

# The function will use its runtime service account for authentication.
# This service account needs "Storage Object Viewer" on the GCS bucket.
gcloud functions deploy private-gallery-backend \
    --gen2 \
    --runtime=python312 \
    --project=photos-by-463514 \
    --region=australia-southeast1 \
    --source=. \
    --entry-point=private_gallery_backend \
    --trigger-http \
    --allow-unauthenticated \
    --set-env-vars="GCS_BUCKET_NAME=photos-by-logan-content"

echo ""
echo "Deployment command sent successfully."
