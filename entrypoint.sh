#!/bin/sh

PUID=${PUID:-1000}
PGID=${PGID:-1000}
SPOOLMAN_PORT=${SPOOLMAN_PORT:-8000}
SPOOLMAN_HOST=${SPOOLMAN_HOST:-0.0.0.0}

groupmod -o -g "$PGID" app
usermod -o -u "$PUID" app

echo User UID: $(id -u app)
echo User GID: $(id -g app)

# Fix permissions on USB printer device if present
for dev in /dev/usb/lp*; do
    [ -e "$dev" ] && chmod 666 "$dev" && echo "Enabled access to $dev"
done

echo "Starting uvicorn..."

# Execute the uvicorn command with any additional arguments
exec gosu "app" uvicorn spoolman.main:app --host $SPOOLMAN_HOST --port $SPOOLMAN_PORT "$@"
