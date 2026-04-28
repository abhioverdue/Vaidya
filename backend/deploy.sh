#!/bin/bash
# Vaidya backend — one-command redeploy
# Usage: bash deploy.sh
# Requires: AWS CLI configured, Docker running

set -e

# ── Config ────────────────────────────────────────────────────────────────────
AWS_REGION="ap-south-2"
CLUSTER="vaidya-cluster"
SERVICE="vaidya-service"
TASK_FAMILY="vaidya-task"
CONTAINER_NAME="vaidya-backend"
HEALTH_URL="http://18.60.50.83:8000/health"

# Derive ECR repo from current task definition (no hardcoding needed)
CURRENT_IMAGE=$(aws ecs describe-task-definition \
  --task-definition "$TASK_FAMILY" \
  --region "$AWS_REGION" \
  --query "taskDefinition.containerDefinitions[0].image" \
  --output text)

ECR_REPO=$(echo "$CURRENT_IMAGE" | cut -d: -f1)
echo "ECR repo: $ECR_REPO"

# ── Step 1: Build & push image ────────────────────────────────────────────────
echo ""
echo "==> Building Docker image..."
cd "$(dirname "$0")"
docker build --target production --platform linux/amd64 -t vaidya-backend:latest .

echo "==> Pushing to ECR..."
aws ecr get-login-password --region "$AWS_REGION" | \
  docker login --username AWS --password-stdin "$ECR_REPO"

docker tag vaidya-backend:latest "$ECR_REPO:latest"
docker push "$ECR_REPO:latest"

# ── Step 2: Patch env vars in live task definition ────────────────────────────
# Pulls the current task def, updates REDIS_URL, registers new revision.
# Everything else (CPU, memory, roles, log config) is preserved automatically.
echo ""
echo "==> Patching task definition env vars..."

REDIS_URL="rediss://default:gQAAAAAAAYEdAAIncDE4ZDQxMjRlNzNjMTI0MTJlOTI1YmE2MjM5MjljMTdmM3AxOTg1ODk@on-termite-98589.upstash.io:6379"

# Fetch current task def, patch env vars, write to temp file
TMPFILE="$(pwd)/taskdef-patch.json"
TMPRAW="$(pwd)/taskdef-raw.json"

aws ecs describe-task-definition \
  --task-definition "$TASK_FAMILY" \
  --region "$AWS_REGION" \
  --query "taskDefinition" \
  --output json > "$TMPRAW"

python3 - "$TMPRAW" "$REDIS_URL" "$CONTAINER_NAME" > "$TMPFILE" << 'PYEOF'
import json, sys

raw_path  = sys.argv[1]
redis_url = sys.argv[2]
cname     = sys.argv[3]

with open(raw_path) as f:
    td = json.load(f)

for key in ['taskDefinitionArn','revision','status','requiresAttributes',
            'compatibilities','registeredAt','registeredBy','deregisteredAt']:
    td.pop(key, None)

# Env vars to force-set (override anything in the old task revision)
FORCE_ENV = {
    'REDIS_URL':    redis_url,
    'GEMINI_MODEL': 'gemini-2.5-flash',
}

for container in td.get('containerDefinitions', []):
    if container['name'] == cname:
        env = container.get('environment', [])
        for e in env:
            if e['name'] in FORCE_ENV:
                e['value'] = FORCE_ENV.pop(e['name'])
        # Append any keys not already present
        for k, v in FORCE_ENV.items():
            env.append({'name': k, 'value': v})
        container['environment'] = env

print(json.dumps(td))
PYEOF

# Convert Unix-style Git Bash path to Windows path for AWS CLI
WIN_TMPFILE="$(cd "$(dirname "$TMPFILE")" && pwd -W)/$(basename "$TMPFILE")"

# Register the new revision
NEW_REVISION=$(aws ecs register-task-definition \
  --region "$AWS_REGION" \
  --cli-input-json "file://$WIN_TMPFILE" \
  --query "taskDefinition.revision" \
  --output text)

rm -f "$TMPFILE" "$TMPRAW"
echo "Registered $TASK_FAMILY:$NEW_REVISION"

# ── Step 3: Update the service ────────────────────────────────────────────────
echo ""
echo "==> Updating ECS service to $TASK_FAMILY:$NEW_REVISION ..."
aws ecs update-service \
  --cluster "$CLUSTER" \
  --service "$SERVICE" \
  --task-definition "$TASK_FAMILY:$NEW_REVISION" \
  --force-new-deployment \
  --region "$AWS_REGION" \
  --output text --query "service.serviceName" > /dev/null

echo "==> Waiting for service to stabilise (this takes ~2 min)..."
aws ecs wait services-stable \
  --cluster "$CLUSTER" \
  --services "$SERVICE" \
  --region "$AWS_REGION"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "Deploy complete."
echo "Health check: $(curl -sf $HEALTH_URL || echo 'FAILED — check ECS logs')"
