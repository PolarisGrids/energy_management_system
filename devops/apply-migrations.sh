#!/usr/bin/env bash
# Run Alembic migrations against the live polaris-ems-backend pod's DB.
#
# Usage:
#   ./devops/apply-migrations.sh stamp    # first run only — mark existing schema as baseline
#   ./devops/apply-migrations.sh upgrade  # apply new revisions
#   ./devops/apply-migrations.sh current  # show current revision
#
# The CodeBuild pipeline deliberately does NOT run migrations so a broken
# migration cannot be auto-deployed. Run this manually from a machine with
# kubectl access to `dev-cluster` and the `polaris-ems` namespace.

set -euo pipefail

NAMESPACE="${NAMESPACE:-polaris-ems}"
DEPLOYMENT="${DEPLOYMENT:-polaris-ems-backend}"
ACTION="${1:-}"

if [[ -z "$ACTION" ]]; then
    echo "usage: $0 {stamp|upgrade|current|downgrade <rev>}" >&2
    exit 2
fi

POD=$(kubectl -n "$NAMESPACE" get pods -l app="$DEPLOYMENT" -o jsonpath='{.items[0].metadata.name}')
if [[ -z "$POD" ]]; then
    echo "No pod found for $DEPLOYMENT in $NAMESPACE" >&2
    exit 1
fi

echo "Using pod: $POD"
case "$ACTION" in
    stamp)
        # Only needed the first time we're activating Alembic on an existing
        # create_all()-seeded DB. Stamps the current schema as the head revision.
        REV="${2:-head}"
        kubectl -n "$NAMESPACE" exec -it "$POD" -- alembic stamp "$REV"
        ;;
    upgrade)
        kubectl -n "$NAMESPACE" exec -it "$POD" -- alembic upgrade head
        ;;
    current)
        kubectl -n "$NAMESPACE" exec -it "$POD" -- alembic current
        ;;
    downgrade)
        [[ -z "${2:-}" ]] && { echo "downgrade requires a revision id"; exit 2; }
        kubectl -n "$NAMESPACE" exec -it "$POD" -- alembic downgrade "$2"
        ;;
    *)
        echo "unknown action: $ACTION" >&2
        exit 2
        ;;
esac
