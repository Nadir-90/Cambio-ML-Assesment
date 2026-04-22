#!/bin/bash
set -e

# Read session config injected by ContainerManager via environment variables
SESSION_USERNAME="${SESSION_USERNAME:-computeruse}"
SESSION_HOME="${SESSION_HOME:-/home/$SESSION_USERNAME}"
export DISPLAY=:1
export DISPLAY_NUM=1
export WIDTH="${WIDTH:-1024}"
export HEIGHT="${HEIGHT:-768}"

echo "Starting session container: user=$SESSION_USERNAME home=$SESSION_HOME"

# Create session user at runtime if not the build-time default
if [ "$SESSION_USERNAME" != "computeruse" ]; then
    if ! id "$SESSION_USERNAME" &>/dev/null; then
        useradd -m -s /bin/bash -d "$SESSION_HOME" "$SESSION_USERNAME"
        echo "$SESSION_USERNAME ALL=(ALL) NOPASSWD: ALL" > "/etc/sudoers.d/$SESSION_USERNAME"
        chmod 440 "/etc/sudoers.d/$SESSION_USERNAME"
    fi
    # Copy desktop configs from build-time user to session user
    mkdir -p "$SESSION_HOME/.tint2"
    cp -r /home/computeruse/.tint2/. "$SESSION_HOME/.tint2/"
    # Rewrite hardcoded /home/computeruse paths to this session user's home
    sed -i "s|/home/computeruse|$SESSION_HOME|g" "$SESSION_HOME/.tint2/tint2rc"
    chown -R "$SESSION_USERNAME:$SESSION_USERNAME" "$SESSION_HOME"
fi

chmod 1777 /tmp/.X11-unix 2>/dev/null || true

# Start virtual display
echo "Starting Xvfb on :1..."
Xvfb :1 -ac -screen 0 "${WIDTH}x${HEIGHT}x24" -retro -dpi 96 &

# Wait for display to be ready
for i in $(seq 1 30); do
    DISPLAY=:1 xdpyinfo >/dev/null 2>&1 && break
    sleep 0.3
done
DISPLAY=:1 xdpyinfo >/dev/null 2>&1 || { echo "Xvfb failed to start"; exit 1; }
echo "Xvfb ready on :1"

# Start window manager as session user
sudo -u "$SESSION_USERNAME" \
    env DISPLAY=:1 HOME="$SESSION_HOME" XDG_SESSION_TYPE=x11 \
    mutter --replace --sm-disable >/tmp/mutter.log 2>&1 &
sleep 2

# Start taskbar as session user
sudo -u "$SESSION_USERNAME" \
    env DISPLAY=:1 HOME="$SESSION_HOME" \
    tint2 -c "$SESSION_HOME/.tint2/tint2rc" >/tmp/tint2.log 2>&1 &
sleep 1

# Start x11vnc so websockify in the main app can reach it
x11vnc -display :1 -forever -shared -wait 50 -rfbport 5900 -nopw >/tmp/x11vnc.log 2>&1 &

# Wait for x11vnc to be ready
for i in $(seq 1 15); do
    netstat -tuln | grep -q ":5900 " && break
    sleep 1
done
echo "x11vnc ready on port 5900"

# Start the tool server (exposes tools over HTTP on port 8001)
echo "Starting tool server on port 8001..."
exec python3 /opt/cua-session/tool_server.py
