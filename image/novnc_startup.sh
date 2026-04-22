#!/bin/bash

echo "starting noVNC (token-based routing mode)"

# Backend populates this token file dynamically
touch /tmp/vnc_tokens.cfg

/opt/noVNC/utils/websockify/run \
    --web /opt/noVNC \
    --token-plugin TokenFile \
    --token-source /tmp/vnc_tokens.cfg \
    6080 \
    > /tmp/novnc.log 2>&1 &

timeout=15
while [ $timeout -gt 0 ]; do
    if netstat -tuln | grep -q ":6080 "; then
        break
    fi
    sleep 1
    ((timeout--))
done

if [ $timeout -eq 0 ]; then
    echo "noVNC failed to start — last log:" >&2
    cat /tmp/novnc.log >&2
    exit 1
fi

echo "noVNC started successfully (token routing on port 6080)"
