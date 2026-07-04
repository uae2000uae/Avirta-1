#!/bin/bash
# === Avirta: stop question-data pushes from triggering a Cloud Run deploy ===
# Adds `contents/questions/**` to the Cloud Build trigger's ignoredFiles so a
# push that ONLY changes question JSON does not start a build/deploy. Pushes that
# also change code still deploy normally.
#
# Usage:
#   ./configure-deploy-trigger.sh <TRIGGER_NAME> [comma,separated,globs]
#
# Env overrides:  REGION (default us-central1)
set -e

REGION="${REGION:-us-central1}"
TRIGGER="$1"
PATTERNS="${2:-contents/questions/**,questionmanagement/reported_questions/**,datastore/usage/**}"

if [ -z "$TRIGGER" ]; then
  echo "Usage: ./configure-deploy-trigger.sh <TRIGGER_NAME> [comma,separated,globs]"
  echo
  echo "Triggers in region '$REGION':"
  gcloud builds triggers list --region="$REGION" \
    --format="table(name, github.name, filename)" 2>/dev/null \
    || gcloud builds triggers list --format="table(name)"
  echo
  echo "If your trigger is global (no region), re-run with:  REGION= ./configure-deploy-trigger.sh <name>"
  exit 1
fi

REGION_FLAG=""
[ -n "$REGION" ] && REGION_FLAG="--region=$REGION"

TMP="$(mktemp).yaml"
echo "Exporting trigger '$TRIGGER'..."
gcloud builds triggers export "$TRIGGER" $REGION_FLAG --destination="$TMP"

python3 "$(dirname "$0")/_deploy_trigger_ignore.py" "$TMP" "$PATTERNS"

echo "Importing updated trigger..."
gcloud builds triggers import $REGION_FLAG --source="$TMP"
rm -f "$TMP"

echo
echo "Done. Pushes that only touch [$PATTERNS] will no longer trigger a deploy."
