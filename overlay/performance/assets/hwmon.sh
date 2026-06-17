#!/bin/bash
# Speist die Performance-Anzeige der WayVR-Watch (yakuda-connect).
# Schreibt die Werte live ueber 'wayvrctl batch' in die Labels der watch.xml.
#
# WICHTIG: Pro Durchlauf wird eine FRISCHE 'wayvrctl batch'-Verbindung benutzt.
# So funktioniert die Anzeige auch dann weiter, wenn die watch.xml neu geladen
# wird (z. B. beim Ein-/Ausschalten der SlimeVR-Buttons) — eine dauerhaft offene
# Verbindung wuerde sonst auf das alte, ersetzte Panel zeigen.

# Erzwingt Dezimalpunkt + englische Labels (sensors), unabhaengig von der Systemsprache.
export LC_ALL=C

# GPU-Auslastungs-Datei automatisch finden (card0 / card1 / ...)
gpu_busy_file=""
for f in /sys/class/drm/card*/device/gpu_busy_percent; do
    [ -r "$f" ] && gpu_busy_file="$f" && break
done

prev_idle=0
prev_total=0

while true; do
    # --- CPU-Auslastung ueber /proc/stat (Delta ueber 1s, locale-unabhaengig) ---
    read -r _ u n s i io irq sirq steal _ < /proc/stat
    total=$((u + n + s + i + io + irq + sirq + steal))
    d_idle=$((i - prev_idle))
    d_total=$((total - prev_total))
    if [ "$d_total" -gt 0 ]; then
        cpu_usage=$(( (100 * (d_total - d_idle)) / d_total ))
    else
        cpu_usage=0
    fi
    prev_idle=$i
    prev_total=$total

    # --- Temperaturen via sensors ---
    cpu_temp=$(sensors 2>/dev/null | grep -i "Tctl:"     | head -1 | awk '{print $2}' | tr -d '+°C' | cut -d'.' -f1)
    gpu_temp=$(sensors 2>/dev/null | grep -i "edge:"     | head -1 | awk '{print $2}' | tr -d '+°C' | cut -d'.' -f1)
    gpu_jnc=$( sensors 2>/dev/null | grep -i "junction:" | head -1 | awk '{print $2}' | tr -d '+°C' | cut -d'.' -f1)
    [ -z "$cpu_temp" ] && cpu_temp="--"
    [ -z "$gpu_temp" ] && gpu_temp="--"
    [ -z "$gpu_jnc" ]  && gpu_jnc="--"

    # --- GPU-Auslastung ---
    gpu_usage="0"
    [ -n "$gpu_busy_file" ] && gpu_usage=$(cat "$gpu_busy_file" 2>/dev/null)
    [ -z "$gpu_usage" ] && gpu_usage="0"

    # --- Gewuenschte Sichtbarkeit aus Zustandsdatei lesen (Standard: sichtbar) ---
    hwmon_visible=1
    [ -f "$HOME/.config/wayvr/.hwmon_visible" ] && hwmon_visible=$(cat "$HOME/.config/wayvr/.hwmon_visible" 2>/dev/null)
    [ "$hwmon_visible" = "0" ] || hwmon_visible=1

    # --- Werte in einer FRISCHEN batch-Sitzung schreiben (ueberlebt Reloads) ---
    {
        echo "panel-modify watch hwmon_box set-visible ${hwmon_visible}"
        echo "panel-modify watch cputemp  set-text \"cpu temp: ${cpu_temp}°C\""
        echo "panel-modify watch cpuusage set-text \"cpu: ${cpu_usage}%\""
        echo "panel-modify watch gputemp  set-text \"gpu temp: ${gpu_temp}°C\""
        echo "panel-modify watch gpujnc   set-text \"junc: ${gpu_jnc}°C\""
        echo "panel-modify watch gpuusage set-text \"gpu: ${gpu_usage}%\""
    } | wayvrctl batch 2>/dev/null

    sleep 1
done
