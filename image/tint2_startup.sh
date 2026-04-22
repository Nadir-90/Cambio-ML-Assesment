#!/bin/bash
echo "starting tint2 on display :$DISPLAY_NUM ..."

tint2 -c $HOME/.tint2/tint2rc 2>/tmp/tint2_stderr.log &

timeout=30
while [ $timeout -gt 0 ]; do
    if xdotool search --class "tint2" >/dev/null 2>&1; then
        break
    fi
    sleep 1
    ((timeout--))
done

if [ $timeout -eq 0 ]; then
    echo "tint2 stderr output:" >&2
    cat /tmp/tint2_stderr.log >&2
    exit 1
fi

rm /tmp/tint2_stderr.log
