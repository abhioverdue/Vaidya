#!/bin/bash
set -e
until pg_isready -h postgres -U ${POSTGRES_USER:-vaidya}; do
  echo "Waiting for Postgres..."
  sleep 2
done
exec "$@"