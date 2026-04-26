#!/usr/bin/env bash
set -euo pipefail

API="${API:-http://127.0.0.1:8000}"

if [ "$#" -lt 2 ]; then
  echo "Usage:"
  echo "  ./scripts/accept_claims_for_project.sh PROJECT_ID CLAIM_ID 
[CLAIM_ID ...]"
  exit 1
fi

PROJECT_ID="$1"
shift

for CLAIM_ID in "$@"; do
  echo "Processing claim $CLAIM_ID"

  curl -s -X POST "$API/claims/$CLAIM_ID/link" \
    -H "Content-Type: application/json" \
    -d "{\"project_id\":\"$PROJECT_ID\"}" >/dev/null

  curl -s -X POST "$API/claims/$CLAIM_ID/review" \
    -H "Content-Type: application/json" \
    -d '{
      "review_status": "accepted_candidate",
      "reviewer": "test@local",
      "notes": "Accepted via safe claim script.",
      "is_contradictory": false
    }' >/dev/null

  curl -s -X POST "$API/claims/$CLAIM_ID/accept" \
    -H "Content-Type: application/json" \
    -d '{
      "accepted_by": "test@local",
      "notes": "Accepted via safe claim script."
    }' >/dev/null
done

echo "Done."
echo "Project evidence:"
curl -s "$API/projects/$PROJECT_ID/evidence"
echo ""
