#!/bin/sh
# Platform volumes usually arrive owned by root: fix ownership of the data folder, then run the service as an unprivileged user.
# If a replica is configured (OFFSITE_BUCKET for S3-compatible storage, or LITESTREAM_FILE_REPLICA for a plain folder), Litestream streams every database change to it
# (about a second behind) and, when the disk comes up EMPTY, first restores the database from the replica. Without a replica the service just starts.
set -e
DATA="${ENGINE_DATA:-/data}"
DB="$DATA/engine.db"
mkdir -p "$DATA"
chown -R engine:engine "$DATA" 2>/dev/null || true
AS="setpriv --reuid=engine --regid=engine --init-groups"

REPLICA=""
if [ -n "$LITESTREAM_FILE_REPLICA" ]; then
  mkdir -p "$LITESTREAM_FILE_REPLICA"; chown -R engine:engine "$LITESTREAM_FILE_REPLICA" 2>/dev/null || true
  REPLICA="      type: file
      path: $LITESTREAM_FILE_REPLICA"
elif [ -n "$OFFSITE_BUCKET" ] && [ "${LITESTREAM:-1}" = "1" ]; then
  REPLICA="      type: s3
      bucket: $OFFSITE_BUCKET
      path: ${LITESTREAM_PREFIX:-litestream/engine}
      region: ${AWS_REGION:-us-east-1}"
  [ -n "$OFFSITE_ENDPOINT" ] && REPLICA="$REPLICA
      endpoint: $OFFSITE_ENDPOINT
      force-path-style: true"
fi

if [ -n "$REPLICA" ]; then
  cat > /tmp/litestream.yml <<YML
addr: "127.0.0.1:9191"
dbs:
  - path: $DB
    replica:
$REPLICA
      sync-interval: 1s
YML
  export LITESTREAM_METRICS=127.0.0.1:9191
  if [ ! -f "$DB" ]; then
    echo "entrypoint: no database on this disk; restoring from the replica if there is one"
    $AS litestream restore -if-replica-exists -config /tmp/litestream.yml "$DB" || echo "entrypoint: restore failed; refusing to start on an empty database" >&2
    if [ ! -f "$DB" ] && [ "${ALLOW_FRESH_START:-0}" != "1" ] && [ -n "$LITESTREAM_REQUIRE_REPLICA" ]; then exit 1; fi
  fi
  exec $AS litestream replicate -config /tmp/litestream.yml -exec "$*"
fi
exec $AS "$@"
