#!/bin/bash
# Upload verified articles to S3 and re-index the Knowledge Base.
# Needs BUCKET, KB_ID and DS_ID set, e.g. in your shell or a local .env.
set -euo pipefail

cd "$(dirname "$0")/.."
[ -f .env ] && source .env

: "${BUCKET:?set BUCKET}"
: "${KB_ID:?set KB_ID}"
: "${DS_ID:?set DS_ID}"

python scripts/build_articles.py
aws s3 sync build/articles "s3://$BUCKET/articles" --delete

aws bedrock-agent start-ingestion-job \
  --knowledge-base-id "$KB_ID" \
  --data-source-id "$DS_ID" \
  --query 'ingestionJob.ingestionJobId' --output text
