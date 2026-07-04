#!/bin/bash
# === Avirta: deploy a new revision WITHOUT taking traffic ===
# Ships a new Cloud Run revision tagged "next" that receives 0% traffic, so any
# in-progress games keep running on the current live revision. Test it via the
# tagged preview URL, then run ./promote-latest.sh to switch traffic over
# (do that during a lull, since the cutover drains the old revision).
set -e

SERVICE_NAME="${SERVICE_NAME:-avirta}"
REGION="${REGION:-us-central1}"
TAG="${TAG:-next}"

echo "Deploying '$SERVICE_NAME' to region '$REGION' with NO traffic (tag: $TAG)..."
gcloud run deploy "$SERVICE_NAME" \
  --source . \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --port 8080 \
  --set-secrets OPENAI_API_KEY=OPENAI_API_KEY:latest,GITHUB_TOKEN=GITHUB_TOKEN:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest \
  --no-traffic \
  --tag "$TAG"

echo
echo "New revision deployed with 0% traffic. Preview/test it here:"
gcloud run services describe "$SERVICE_NAME" --region "$REGION" \
  --format="value(status.traffic.filter('tag', '$TAG').url)" 2>/dev/null \
  || echo "  (find the '$TAG' tagged URL in the Cloud Run console)"
echo
echo "When you're ready (ideally no active games), promote it:"
echo "  ./promote-latest.sh"
