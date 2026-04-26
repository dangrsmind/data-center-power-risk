API="http://127.0.0.1:8000"
PROJECT_ID="9fae64af-1ba2-4ac1-93bf-08e065180d7b"

for CLAIM_ID in \
  "3ee8d922-ab8b-480c-9fe5-239094140d65" \
  "4622839b-aae7-41c6-aea9-6ee57e21e63c" \
  "ace4d989-6eca-434d-b310-31f779f00e10" \
  "1a5d09ed-4b96-4e8e-bebf-a59e10101a26"
do
  echo "Processing claim $CLAIM_ID"

  curl -s -X POST "$API/claims/$CLAIM_ID/link" \
    -H "Content-Type: application/json" \
    -d "{\"project_id\":\"$PROJECT_ID\"}" >/dev/null

  curl -s -X POST "$API/claims/$CLAIM_ID/review" \
    -H "Content-Type: application/json" \
    -d '{
      "review_status": "accepted_candidate",
      "reviewer": "test@local",
      "notes": "Accepted from safe CleanArc pilot claim.",
      "is_contradictory": false
    }' >/dev/null

  curl -s -X POST "$API/claims/$CLAIM_ID/accept" \
    -H "Content-Type: application/json" \
    -d '{
      "accepted_by": "test@local",
      "notes": "Accepted from safe CleanArc pilot claim."
    }' >/dev/null
done

echo "Done. Verifying project evidence:"
curl -s "$API/projects/$PROJECT_ID/evidence"
