#!/bin/bash
# Blendet die Performance-Box (id="hwmon_box") in der WayVR-Watch ein/aus.
STATE="$HOME/.config/wayvr/.hwmon_visible"
cur=1
[ -f "$STATE" ] && cur=$(cat "$STATE" 2>/dev/null)
if [ "$cur" = "1" ]; then new=0; else new=1; fi
echo "$new" > "$STATE"
wayvrctl panel-modify watch hwmon_box set-visible "$new" 2>/dev/null
