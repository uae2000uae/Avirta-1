#!/bin/bash
# === Avirta: send 100% traffic to the latest revision ===
# Flip traffic to the newest revision deployed via ./deploy-no-traffic.sh.
# NOTE: the cutover drains the current revision, so any in-memory games on it
# will end. Run this during a lull (or accept a brief interruption) until game
# state is externalized to Firestore/Redis.
set -e

SERVICE_NAME="${SERVICE_NAME:-avirta}"
REGION="${REGION:-us-central1}"

echo "Routing 100% traffic to the latest revision of '$SERVICE_NAME'..."
gcloud run services update-traffic "$SERVICE_NAME" --region "$REGION" --to-latest
echo "Done. Latest revision is now live."
