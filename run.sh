#!/bin/sh
#
# Start Control Center on the command line.
# This way of starting is useful for development, not for production servers.

if [ -z "$TWIST" ]
then
    if which twist3 >/dev/null 2>&1
    then
        # Make sure we get the Python 3 version.
        TWIST=twist3
    else
        # Use default one and hope it's Python 3.
        TWIST=twist
    fi
fi

PYTHONPATH=src/softfab "$TWIST" web \
    --listen tcp:interface=127.0.0.1:port=8180 \
    --class TwistedApp.Root
