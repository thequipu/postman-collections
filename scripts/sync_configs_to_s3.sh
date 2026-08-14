#!/bin/bash
# ============================================================
# Push local test config/secrets INTO S3 (upload side of the CI pipeline).
#
# The Jenkins job DOWNLOADS these at test time:
#   aws s3 sync s3://$BUCKET/config/environments/ api-tests/environments/
#   aws s3 sync s3://$BUCKET/config/secrets/      api-tests/secrets/
#   aws s3 sync s3://$BUCKET/config/db-configs/   api-tests/db-configs/
# This utility is the reverse — run it after editing local configs to publish them.
#
# Usage:
#   ./scripts/sync_configs_to_s3.sh                      # bucket: quipu-api-tests
#   ./scripts/sync_configs_to_s3.sh my-bucket            # custom bucket
#   S3_TEST_BUCKET=my-bucket ./scripts/sync_configs_to_s3.sh
#   DRY_RUN=1 ./scripts/sync_configs_to_s3.sh            # preview only
#
# Prereqs: AWS CLI configured with S3 write permission on the bucket.
# ============================================================
set -euo pipefail

BUCKET="${1:-${S3_TEST_BUCKET:-quipu-api-tests}}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DRY="${DRY_RUN:+--dryrun}"

echo "=== Syncing local config -> s3://${BUCKET}/config/ ${DRY:+(DRY RUN)} ==="

# db-configs: DB configs + S3 datasource configs (csv/excel carry the AWS creds)
if [ -d "${ROOT}/config/db-configs" ]; then
    aws s3 sync "${ROOT}/config/db-configs/" "s3://${BUCKET}/config/db-configs/" \
        --exclude "*" --include "*.json" ${DRY}
    echo "  db-configs synced ($(ls "${ROOT}"/config/db-configs/*.json 2>/dev/null | wc -l) files)"
fi

# secrets: *.secrets.env (gitignored locally, live only in S3)
if [ -d "${ROOT}/config/secrets" ]; then
    aws s3 sync "${ROOT}/config/secrets/" "s3://${BUCKET}/config/secrets/" \
        --exclude "*" --include "*.env" ${DRY}
    echo "  secrets synced"
fi

# environments: Postman environment overrides
if [ -d "${ROOT}/environments" ]; then
    aws s3 sync "${ROOT}/environments/" "s3://${BUCKET}/config/environments/" \
        --exclude "*" --include "*.postman_environment.json" ${DRY}
    echo "  environments synced"
fi

echo "=== Done. Contents: ==="
aws s3 ls "s3://${BUCKET}/config/db-configs/"
