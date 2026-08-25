# yakuda-connect

**A sleek and intuitive GUI for WiVRn — Linux VR streaming made easy.**

[![Discord](https://img.shields.io/badge/Join_Our_Discord-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discord.gg/X5TaN4A47h)
[![Ko-fi](https://img.shields.io/badge/Support_me_on_Ko--fi-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white)](https://ko-fi.com/yakuda_)
[![Version](https://img.shields.io/badge/Version-v1.2.4-81a1c1?style=for-the-badge)](https://github.com/yakuda-stack/yakuda-connect/releases)

`yakuda-connect` is a powerful configuration hub and dashboard for Linux VR. It eliminates the need for complex terminal commands, allowing you to manage, configure, and launch your WiVRn environment with a single click.

### 🐧 Tested systems

| System | Status | Notes |
|---|---|---|
| **Arch-based** | ✅ Tested — primary development system | Full feature set: AUR installation, all components |
| **Fedora-based** | ✅ Tested | Components come from the Fedora repos; xrizer from the COPR `@xr-sig/xrizer` or the GitHub release. The WiVRn dashboard is deliberately not offered here — yakuda-connect already provides the controls |
| Debian / Ubuntu / Linux Mint | ✅ Tested (Mint 22.3) | WiVRn from the Linux VR Adventures PPA (`ppa:lvra/wivrn`) where it builds, otherwise the Flathub Flatpak; xrizer straight from its GitHub release. Note: the PPA has no build for Ubuntu 24.04 `noble`, the base of Mint 22.x |

### 📸 Interface Preview

<table>
  <tr>
    <td><b>Dashboard</b><br><img src="assets/dashboard.png" alt="Dashboard" width="300"/></td>
    <td><b>Installation</b><br><img src="assets/installation.png" alt="Installation" width="300"/></td>
    <td><b>Streaming Settings</b><br><img src="assets/streaming.png" alt="Streaming" width="300"/></td>
  </tr>
  <tr>
    <td><b>Tools Hub</b><br><img src="assets/tools.png" alt="Tools" width="300"/></td>
    <td><b>General Settings</b><br><img src="assets/settings.png" alt="Settings" width="300"/></td>
    <td><b>Advanced Settings</b><br><img src="assets/settings2.png" alt="Settings 2" width="300"/></td>
  </tr>
  <tr>
    <td><b>Tools Hub</b><br><img src="assets/games1.png" alt="Tools" width="300"/></td>
    <td><b>General Settings</b><br><img src="assets/games2.png" alt="Settings" width="300"/></td>
  </tr>
</table>
<table>
  <tr>
    <td><b>Dashboard</b><br><img src="assets/miau.gif" alt="Dashboard" width="600"/></td>
</table>
---

## 🚀 Key Features

* **Centralized Dashboard:** Start and stop your WiVRn server instantly with a clean, easy-to-use interface.
* **VR Games Library:** The Games tab auto-detects every installed Steam VR game and shows it as a cover tile — with curated Proton profiles and tested launch options for games like VRChat, auto-recommendations for everything else, and one-click **Use** (set Proton version) and **▶ Play** (launch via Steam) buttons.
* **ProtonPlus Integration:** Install the recommended Proton builds (Proton-GE, GE-RTSP, Proton-CachyOS) straight from a game's panel via the ProtonPlus CLI.
* **Advanced Autostart Chain:** Launch multiple VR companion tools (such as WayVR, VRCX, OpenComposite, SlimeVR, or OSC tools) automatically in a custom sequence.
* **OSC Toolbox:** One-click OSC Query fix for supported OSC tools (OSC Leash, OscGoesBrrr) when VRChat OSC acts up.
* **One-Click Environment Setup:** Automated installation of essential WiVRn dependencies and network/firewall configuration (Port 9757).
* **Headset Client Installer:** Easily install and sideload the companion Android client (.apk) directly onto your standalone VR headset (Pico / Quest) via USB.
* **Stream Fine-Tuning:** Configure encoders, toggle OpenVR compatibility, and manage your OpenXR runtimes directly from the UI.
* **Backup & Restore:** Instantly save or recover your entire VR environment configuration.
* **Customizable Interface:** Eight built-in themes plus per-role colour pickers, an optional background image and adjustable card opacity — under Settings → **Design**.
* **Desktop Compatibility:** Runs smoothly across various desktop environments including KDE Plasma, GNOME, and Hyprland.

---

## 📦 Installation & Setup

Whether you are a Linux newcomer or a power user, there are several straightforward ways to get `yakuda-connect` up and running.

### Method 1: AUR (Recommended for Arch, CachyOS, EndeavourOS, Manjaro)

`yakuda-connect` is available in the [AUR](https://aur.archlinux.org/packages/yakuda-connect). Install it with your favourite AUR helper — all dependencies are pulled in automatically, and you get updates through your normal system update:

```bash
yay -S yakuda-connect
```

or

```bash
paru -S yakuda-connect
```

Then launch it from your application menu or simply run:

```bash
yakuda-connect
```

### Method 2: Fedora, Debian, Ubuntu and Linux Mint

The setup script detects the package manager itself (pacman, dnf, apt, zypper) and installs PySide6 from the matching distribution package; if there is none, it builds its own venv, touching neither the system Python nor PEP 668:

```bash
bash <(curl -s https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh) && yakuda-connect
```

The VR components themselves are then installed from within the app (Installation tab). On Fedora they come from the official repos; xrizer is available from the COPR `@xr-sig/xrizer` or, as an alternative, straight from the GitHub release — selectable per component.

### Method 3: Express Installation (AppImage & Terminal)

Choose one of the two options below to get started as quickly as possible:

#### Option A: One-Click Terminal Command (Fastest Method)
Open your terminal and paste the following command. It will automatically download the setup script, install the tool, and launch it immediately:

```bash
bash <(curl -s https://raw.githubusercontent.com/yakuda-stack/yakuda-connect/main/install.sh) && yakuda-connect
```

#### Option B: Manual AppImage (No Installation Required)
1. Navigate to the **Releases** section on GitHub.
2. Download `yakuda-connect-<version>-x86_64.AppImage`. One file for every
   system: it works with **FUSE 3** (Arch, CachyOS, Fedora 40+, Ubuntu 24.04+,
   Bazzite, SteamOS) **and FUSE 2** (Ubuntu 22.04 and earlier, Debian 11/12).
   `libfuse2` does **not** need to be installed — libfuse3 is linked statically
   into the file.
3. Make the file executable:
   - **Via GUI:** Right-click the file -> Properties -> Permissions -> Enable "Allow executing file as program".
   - **Via Terminal:** `chmod +x yakuda-connect-*.AppImage`
4. Double-click the file to launch the dashboard!

> **If it won't start** with an error mentioning `fusermount` or `/dev/fuse`
> (containers, hardened kernels, FUSE disabled), run it unpacked instead — this
> works on every system, it is just slightly slower to start:
> ```bash
> ./yakuda-connect-*.AppImage --appimage-extract-and-run
> ```

> **Something not working?** The app writes a log to `~/.cache/yakuda-connect/app.log`.
> Attaching it to a bug report or Discord message makes problems far easier to track down.
> For more detail, start with `YAKUDA_LOG_LEVEL=DEBUG yakuda-connect`.

---

### Method 4: Manual Installation (From Source)

If you prefer to clone the repository and run the application directly from the source code, execute these commands in your terminal sequence:

1. Clone the repository[cite: 2]:
```bash
git clone https://github.com/yakuda-stack/yakuda-connect.git
```

2. Change to the project directory[cite: 2]:
```bash
cd yakuda-connect
```

3. Run the installation script[cite: 2]:
```bash
bash install.sh
```

---

## 🔒 Privacy & Security

Everything below is taken from the source code, and each claim names the file it can be checked against. If you find a difference between this section and the code, that is a bug — please report it.

### The short version

| Question | Answer |
| --- | --- |
| Telemetry? | **None.** No usage data, no events, no crash reporting. |
| Analytics? | **None.** No analytics SDK is present anywhere in the codebase. |
| Usage data collected? | **None.** Nothing about your usage is recorded or transmitted. |
| Data sent to a server? | **No server exists.** There is no yakuda-connect backend. |
| User account / cloud? | **Not possible.** There is no login, no account and no cloud service. |
| Unique ID / fingerprint? | **None.** Requests carry only `User-Agent: yakuda-connect` — no ID, no hardware or system information. |
| Does it open a port? | **No.** yakuda-connect never listens on a port (no socket is created anywhere in the code). |
| Where does the log go? | `~/.cache/yakuda-connect/app.log` — local only. It leaves your machine only if *you* copy or save it. |

### Outgoing network connections

These are all of them. Only the first two happen without you clicking anything.

| Host | When | Purpose | Source |
| --- | --- | --- | --- |
| `raw.githubusercontent.com` | ~1.5 s after start, automatic | Reads one file and compares its version number with the installed one | `core/install_worker.py` |
| `raw.githubusercontent.com` | ~1.5 s after start, automatic | Version of the game database (`config/games.json`) | `core/games.py` |
| `api.github.com` | Only on click | Finds the latest WiVRn release (APK), AppImage tools and the newest xrizer release | `core/main.py`, `core/appimage_installer.py`, `core/xrizer_github.py` |
| `ppa.launchpadcontent.net` | Only on click, apt systems only | Checks whether the WiVRn PPA has a build for this Ubuntu release before adding it (HEAD request, no download) | `core/appimage_installer.py` |
| `github.com` / `codeload.github.com` | Only on click | Downloads AppImages, the WayVR design, the reference backup, the xrizer release ZIP (into `~/.local/share/xrizer`, no root) | `core/appimage_installer.py`, `core/backup_manager.py`, `core/xrizer_github.py` |
| `shared.fastly.steamstatic.com` | When opening the Games tab | Cover images for detected Steam games, cached locally | `core/games.py` |

Nothing is uploaded to any of these. Every request is a plain download.

**What is received:** release metadata (JSON) from the GitHub API, `.AppImage`/`.apk`/`.tar.gz` files you asked for, the game database, and cover images. Nothing is executed automatically after download; AppImages are verified as ELF-64 binaries before being installed (`core/vrcvideocacher_install.py`, `core/vr_environment.py`).

**No port is opened for yakuda-connect.** The firewall button opens ports for `wivrn-server` — see the table below.

### Ports

| Port | Protocol | Used by | Purpose |
| --- | --- | --- | --- |
| 9757 | TCP + UDP | `wivrn-server` | The connection between the PC and the VR headset |
| 5353 | UDP (mDNS) | `avahi` / `wivrn-server` | Lets the headset discover the PC — without it the server list in the headset stays empty even when 9757 is open |

Defined in `core/firewall.py` (`PORT`, `MDNS_PORT`). On ufw the rule is created as the named application profile `/etc/ufw/applications.d/wivrn` — byte for byte what WiVRn's own dashboard writes (`dashboard/firewall.cpp`). The name matters: WiVRn checks whether that file exists to decide if the firewall still needs setting up, so a plain `ufw allow 9757` would open the port but leave WiVRn asking for setup forever. `ports=9757` without a protocol means TCP *and* UDP in ufw. Only the firewall that is actually active is changed (firewalld or ufw). **nftables and iptables are detected but never modified automatically** — you get the commands to copy instead, because there is no reliably identical place to insert a rule and a misplaced one can take a machine off the network.

### System permissions

Only permissions the program actually uses are listed.

| Permission / access | Purpose | When | Source |
| --- | --- | --- | --- |
| Firewall rule (`pkexec`) | Open ports 9757 and 5353 so the headset can reach the WiVRn server | Only on click on "Fix Firewall" | `core/firewall.py` |
| `CAP_SYS_NICE` (`pkexec setcap`) | Lets `wivrn-server` run reprojection at high priority. A capability on one file — not a permanently elevated process | Only on click on "Enable VR Priority" | `ui/vr_runtime_widget.py` |
| `pkexec` for OpenXR config | Write `active_runtime.json` when the file or its folder belongs to root. The folder is handed back to your user afterwards, so later fixes need no root | Only as a fallback when writing without root fails | `core/openxr_manager.py` |
| `pkexec` for restore | Copy files back to `/usr/share/openxr`, `/opt/xrizer`, `/opt/opencomposite`. A timestamped backup is made first; nothing is deleted | Only on click on "Restore" | `core/backup_manager.py` |
| `sudo` in a terminal | Package installation and updates (`yay`, `paru`, `dnf`). Runs in a **visible terminal window** so you see the package list and enter the password yourself — yakuda-connect never handles your password | Only on click in the Installation tab | `core/install_worker.py` |
| Read `/sys/bus/usb/devices` | Detect a connected headset. Plain file reads, no root, no `lsusb` | Background check | `core/usb_headsets.py` |
| `adb` | Install the WiVRn APK onto the headset and detect USB debugging status. Only called when a headset was found on the bus | Only on click / when a headset is present | `core/main.py`, `core/usb_headsets.py` |

**yakuda-connect is never run as root itself.** Each of the actions above elevates a single command through `pkexec`, which shows the system's own password dialog.

### Files and configuration that can be changed

| Path | What happens | Source |
| --- | --- | --- |
| `~/.config/yakuda-connect/` | This program's own settings, backups and downloaded tools | `core/paths.py` |
| `~/.cache/yakuda-connect/` | Log file, game covers, downloaded APK | `core/paths.py` |
| `~/.config/openxr/1/active_runtime.json` | Which OpenXR runtime is active. Previous file kept as `.bak.<timestamp>` | `core/openxr_manager.py` |
| `~/.config/openvr/` | OpenVR paths (read; written by WiVRn itself) | `core/vr_environment.py` |
| `~/.config/wivrn/config.json` | WiVRn server settings (encoder, bitrate, codec, OpenVR compatibility). Read, changed key by key, written back atomically — never rebuilt | `core/config_manager.py` |
| `~/.config/wivrn/wivrn-dashboard.conf` | Only the `auto_connect_usb` key | `core/wivrn_dashboard.py` |
| `~/.config/wayvr/` | WayVR design. Backed up before every change | `core/overlay_manager.py` |
| `~/.config/OSCLeash/Config.json`, `~/.config/OscGoesBrrr/config.json` | The OSCQuery fix sets exactly one key. Files that do not exist are **not** created | `core/queryfix.py` |
| Steam `config.vdf` / `localconfig.vdf` | Proton version and launch options for a game, when you press "Use" | `core/games.py` |
| `~/.bashrc`, `~/.zshrc` | When installing an AppImage tool: appends one marked block that puts `~/.local/bin` on your `PATH`, only if it is not already there | `core/appimage_installer.py` |
| `~/.local/bin/`, `~/.local/share/applications/` | Launcher scripts and `.desktop` entries for tools you install | `core/appimage_installer.py` |
| `/usr/share/openxr`, `/opt/xrizer`, `/opt/opencomposite` | **Only** when restoring a backup, via `pkexec`, with a timestamped backup first | `core/backup_manager.py` |

### Processes that can be started or stopped

* `wivrn-server` — started and stopped from the Dashboard; output goes to `~/.cache/yakuda-connect/wivrn-server.log`
* `wivrnctl pair` — while pairing mode is active
* Autostart programs — the ones you configured yourself in the Dashboard, plus your own kill commands from Settings → Advanced (these run as a shell command, so they do exactly what you wrote)
* `adb`, `pactl`, `getcap`, `pgrep`, `systemctl` — short queries; `adb` only when a headset is connected

### Diagnostics

The log is written locally and rotates at 1 MB (3 old files kept). Settings → **General & Updates** → *Diagnostics & Log* lets you open it, copy the last part, or save a report containing the log plus version, distribution and the active OpenXR runtime. The VRChat video diagnostic deliberately redacts the resolved stream URL, because it contains your public IP and signatures (`core/vrchat_check.py`).

### Advanced Mode

The switch at the bottom left of the sidebar turns on extra technical information. When enabled, actions that change something on your system show an expandable box with a short explanation, the affected files, the required permissions and the equivalent terminal command with a copy button. **The command is never executed** — there is deliberately no "run" button. No feature behaves differently in Advanced Mode; only the information appears. The existing manual OpenXR fix stays exactly where it was.

---

## 💬 Community & Support

yakuda-connect is a free hobby project — built by VR enthusiasts, for VR enthusiasts.

<table>
  <tr>
    <td align="center" width="50%">
      <h3>💬 Join the Discord</h3>
      <p>Questions, bug reports, feature ideas or just showing off your VR setup — our community is happy to help.</p>
      <a href="https://discord.gg/X5TaN4A47h">
        <img src="https://img.shields.io/badge/discord.gg%2FX5TaN4A47h-5865F2?style=for-the-badge&logo=discord&logoColor=white" alt="Join Discord"/>
      </a>
    </td>
    <td align="center" width="50%">
      <h3>❤️ Support the project</h3>
      <p>If yakuda-connect saved you time (or a headache), you can buy the dev a coffee on Ko-fi. Every contribution keeps Linux VR development going!</p>
      <a href="https://ko-fi.com/yakuda_">
        <img src="https://img.shields.io/badge/ko--fi.com%2Fyakuda__-FF5E5B?style=for-the-badge&logo=ko-fi&logoColor=white" alt="Support me on Ko-fi"/>
      </a>
    </td>
  </tr>
</table>

> 💡 **Tip:** Both buttons are also built right into the app — Settings → **Community & Updates**, where you can also check for new versions with one click.

---

## 📝 Changelog

The full changelog lives in its own file — it is kept in both English and German:

➡️ **[CHANGELOG.md](CHANGELOG.md)**
