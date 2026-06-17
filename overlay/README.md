# overlay/ — WayVR Overlay-Dateien für yakuda-connect

Diese Dateien werden vom Launcher (core/overlay_manager.py) verwendet, NICHT
direkt von Hand installiert.

## performance/   (Performance-Overlay, ersetzt den Chatbox-Bereich)
- watch.xml           : WayVR-Watch mit Live-Performance-Anzeige (hwmon-Block)
- watch_slimevr.xml   : wie watch.xml, zusätzlich mit SlimeVR-Reset-Buttons
- watch_nohwmon.xml   : Variante ohne hwmon (Fallback)
- assets/hwmon.sh     : speist GPU/CPU-Last & -Temp live via `wayvrctl batch`
- assets/songname*.sh : Medien-/Songname-Helfer
- assets/media/*.svg  : Icons für Medien-Steuerung

## slimevr/   (SlimeVR-Reset-Buttons)
- assets/*.svg        : Icons (yaw/full/mounting/mounting-feet-reset, eepyxr)
                        -> werden nach ~/.config/wayvr/theme/assets/ kopiert

Hinweise:
- hwmon.sh ist auf AMD + /sys/class/drm/card1 ausgelegt (sensors: Tctl/edge/junction).
- SlimeVR-Buttons brauchen `solarxr-cli` (und ggf. `eepyxr`) im PATH.
