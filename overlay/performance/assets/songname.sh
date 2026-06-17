#!/bin/bash

exec 3> >(wayvrctl batch)
echo "panel-modify watch listenforsong set-visible 0" >&3
$HOME/.config/wayvr/theme/gui/assets/hwmon.sh &
HW_PID=$!

cleanup() {
    kill $HW_PID 2>/dev/null
    exec 3>&-
    exit 0
}
trap cleanup EXIT SIGTERM SIGINT

last_name=""
while true; do
    name=$(playerctl metadata title 2>/dev/null | cut -c1-20)
    if [ "$name" != "$last_name" ]; then
        if [ -n "$name" ]; then
            echo "panel-modify watch songname set-text \"$name\"" >&3
        else
            echo "panel-modify watch songname set-text \"\"" >&3
        fi
        last_name="$name"
    fi
    
    sleep 2
done