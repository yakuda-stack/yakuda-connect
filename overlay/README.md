# yakuda-connect — WayVR Overlay

Basis-Design (wird per "WayVR-Design aktualisieren" live von GitHub geladen):
  https://github.com/cubee-cb/linux-vr-compat/tree/master/dotfiles/wayvr

SlimeVR-Reset-Buttons (optional, eine Reihe DARUNTER): von sapphire
#wayvr-custom (Discord): https://discord.gg/EHAYe3tTYa

Inhalt:
  watch_slimevr.xml  - aktuelle cubee-Watch + SlimeVR-Reihe darunter
  slimevr/assets/    - eepyxr- und Reset-Icons (von sapphire)

Kein Performance-Overlay mehr: Die fruehere hwmon-Anzeige fuetterte WayVR im
Sekundentakt per IPC und konnte es bei langen Sessions zum Haengen bringen.
Der Update-Knopf entfernt Reste einer solchen alten Installation automatisch.
