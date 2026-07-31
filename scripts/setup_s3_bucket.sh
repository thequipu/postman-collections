#!/bin/bash
# ============================================================
# Setup S3 bucket for API flow test config, secrets, and results
#
# Usage:
#   ./scripts/setup_s3_bucket.sh                    # default bucket: quipu-api-tests
#   ./scripts/setup_s3_bucket.sh my-custom-bucket   # custom bucket name
#
# Prerequisites:
#   - AWS CLI configured with credentials
#   - Proper IAM permissions for S3 operations
# ============================================================

set -e

BUCKET="${1:-quipu-api-tests}"
REGION="${AWS_DEFAULT_REGION:-ap-south-1}"

echo "=== Setting up S3 bucket: ${BUCKET} (region: ${REGION}) ==="

# ── 1. Create bucket if it doesn't exist ──
if aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
    echo "Bucket ${BUCKET} already exists"
else
    echo "Creating bucket ${BUCKET}..."
    aws s3api create-bucket \
        --bucket "${BUCKET}" \
        --region "${REGION}" \
        --create-bucket-configuration LocationConstraint="${REGION}"
    echo "Bucket created"
fi

# ── 2. Create directory structure ──
echo "Creating directory structure..."
for dir in \
    config/environments \
    config/secrets \
    config/db-configs \
    results/latest; do
    aws s3api put-object --bucket "${BUCKET}" --key "${dir}/" > /dev/null
done

# ── 3. Upload environment files ──
echo "Uploading environment files..."
for env_file in environments/*.postman_environment.json; do
    if [ -f "$env_file" ]; then
        filename=$(basename "$env_file")
        aws s3 cp "$env_file" "s3://${BUCKET}/config/environments/${filename}"
        echo "  Uploaded: ${filename}"
    fi
done

# ── 4. Create secrets template files ──
echo "Creating secrets templates..."

# dev/onprem secrets
cat > /tmp/dev.secrets.env << 'EOF'
# Onprem/Dev environment secrets
# Fill in actual values before use
client_secret=
test_username=onpremquipu
test_password=onpremquipu
EOF
aws s3 cp /tmp/dev.secrets.env "s3://${BUCKET}/config/secrets/dev.secrets.env"

# staging secrets
cat > /tmp/staging.secrets.env << 'EOF'
# Staging environment secrets
client_secret=
test_username=
test_password=
EOF
aws s3 cp /tmp/staging.secrets.env "s3://${BUCKET}/config/secrets/staging.secrets.env"

# prod secrets (empty — must be filled via Vault or manually)
cat > /tmp/prod.secrets.env << 'EOF'
# Production environment secrets — DO NOT commit actual values
# Use Vault or inject at runtime
client_secret=
test_username=
test_password=
EOF
aws s3 cp /tmp/prod.secrets.env "s3://${BUCKET}/config/secrets/prod.secrets.env"

# ── 5. Create DB config templates ──
echo "Creating DB config templates..."

cat > /tmp/postgres-healthcare.json << 'EOF'
{
  "driverType": "POSTGRES",
  "dbHost": "207.180.249.216",
  "dbPort": "5433",
  "dbName": "healthcare_management",
  "dbUser": "postgres",
  "dbSchema": "public",
  "driverClassName": "org.postgresql.Driver",
  "realmId": "3316"
}
EOF
aws s3 cp /tmp/postgres-healthcare.json "s3://${BUCKET}/config/db-configs/postgres-healthcare.json"

cat > /tmp/mysql-employee.json << 'EOF'
{
  "driverType": "MYSQL",
  "dbHost": "207.180.249.216",
  "dbPort": "3306",
  "dbName": "employee_policy_info",
  "dbUser": "root",
  "dbSchema": "employee_policy_info",
  "driverClassName": "com.mysql.cj.jdbc.Driver",
  "realmId": "3316"
}
EOF
aws s3 cp /tmp/mysql-employee.json "s3://${BUCKET}/config/db-configs/mysql-employee.json"

cat > /tmp/mariadb-datatype.json << 'EOF'
{
  "driverType": "MARIADB",
  "dbHost": "207.180.249.216",
  "dbPort": "3309",
  "dbName": "datatypetesting_mariadb",
  "dbUser": "root",
  "dbSchema": "datatypetesting_mariadb",
  "driverClassName": "org.mariadb.jdbc.Driver",
  "realmId": "3316"
}
EOF
aws s3 cp /tmp/mariadb-datatype.json "s3://${BUCKET}/config/db-configs/mariadb-datatype.json"

# ── 6. Cleanup temp files ──
rm -f /tmp/dev.secrets.env /tmp/staging.secrets.env /tmp/prod.secrets.env
rm -f /tmp/postgres-healthcare.json /tmp/mysql-employee.json /tmp/mariadb-datatype.json

# ── 7. Verify ──
echo ""
echo "=== S3 Bucket Contents ==="
aws s3 ls "s3://${BUCKET}/" --recursive | head -30

echo ""
echo "=== Setup Complete ==="
echo "Bucket:        s3://${BUCKET}"
echo "Environments:  s3://${BUCKET}/config/environments/"
echo "Secrets:       s3://${BUCKET}/config/secrets/"
echo "DB Configs:    s3://${BUCKET}/config/db-configs/"
echo "Results:       s3://${BUCKET}/results/"
echo ""
echo "IMPORTANT: Update secrets files with actual values:"
echo "  aws s3 cp s3://${BUCKET}/config/secrets/dev.secrets.env /tmp/dev.secrets.env"
echo "  # Edit /tmp/dev.secrets.env with real client_secret"
echo "  aws s3 cp /tmp/dev.secrets.env s3://${BUCKET}/config/secrets/dev.secrets.env"
