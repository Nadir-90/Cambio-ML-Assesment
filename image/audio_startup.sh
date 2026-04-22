#!/bin/bash
set -e

echo "starting PulseAudio..."

pulseaudio --start --exit-idle-time=-1 --daemonize=true
sleep 0.5

pactl load-module module-null-sink \
  sink_name=virtual_speaker \
  sink_properties=device.description="Virtual_Speaker" > /dev/null

pactl set-default-sink virtual_speaker

pactl load-module module-simple-protocol-tcp \
  rate=44100 format=s16le channels=2 \
  source=virtual_speaker.monitor \
  record=true port=4713 listen=127.0.0.1 > /dev/null

echo "PulseAudio ready (virtual sink on port 4713)"

/opt/noVNC/utils/websockify/run \
    4680 \
    localhost:4713 \
    > /tmp/audio_ws.log 2>&1 &

timeout=15
while [ $timeout -gt 0 ]; do
    if netstat -tuln | grep -q ":4680 "; then
        break
    fi
    sleep 1
    ((timeout--))
done

if [ $timeout -eq 0 ]; then
    echo "audio websockify failed to start — last log:" >&2
    cat /tmp/audio_ws.log >&2
    exit 1
fi

echo "audio websockify started on port 4680"
