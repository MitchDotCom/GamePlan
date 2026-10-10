#!/bin/sh
# Platform volumes usually arrive owned by root. Fix ownership of the data folder, then drop to an unprivileged user for the service itself.
set -e
mkdir -p "${ENGINE_DATA:-/data}"
chown -R engine:engine "${ENGINE_DATA:-/data}" 2>/dev/null || true
exec setpriv --reuid=engine --regid=engine --init-groups "$@"
