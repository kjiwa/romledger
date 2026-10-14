# Play your library

romledger fills `roms/<platform>/` in your library. Pick a front end that reads that layout, then an
emulator for each platform. Everything here was read from the projects' own pages when this guide
was written; items marked unverified could not be confirmed there.

## Choose a front end

| You want | Use |
| --- | --- |
| Play in a browser, on any device, with saves kept on the server | [RomM](https://romm.app) |
| An Android handheld | [Argosy Launcher](https://github.com/rommapp/argosy-launcher), a RomM client |
| Windows | [Playnite](https://playnite.link) with the [RomM plugin](https://github.com/rommapp/playnite-plugin) |
| Linux or macOS, local files | [ES-DE](https://es-de.org/) |
| Linux, everything in one package | [RetroDECK](https://retrodeck.net/) |

### RomM

RomM expects `roms/<platform>/` in the library, with optional `bios/<platform>/` beside it, and
the platform folder names must match its slugs, such as `nes`, `snes`, `gba`, `3ds`, `dc` and
`psx`. Mount the parent of `roms/` as `/romm/library`
([folder structure](https://docs.romm.app/4.9.0/getting-started/folder-structure/)). Folder names
that differ can be remapped with `system.platforms` in RomM's `config.yml`.

The Play button runs [EmulatorJS](https://docs.romm.app/4.9.0/using/in-browser-play/emulatorjs/)
in the browser for platforms such as NES, SNES, Game Boy, DS, N64, Genesis, PS1, PSP and Saturn.
GameCube, Wii and PS2 are not in its list. Saves and states are written to the server.

To pick up games that `import` filed, schedule a rescan with `SCAN_INTERVAL_CRON` (default
midnight daily; restart the container to apply). RomM also documents a filesystem watcher, but its
pages name the setting two ways, so check the
[environment variables](https://docs.romm.app/4.9.0/reference/environment-variables/) page.

### Android

Argosy Launcher is made for gamepad handhelds on Android 8.0 or later. It syncs your RomM
library, downloads games on demand, starts RetroArch or another emulator you configure, and syncs
saves. Install it from the APK on the
[releases page](https://github.com/rommapp/argosy-launcher); its README names no other source.

### Windows

1. Install Playnite and an emulator for each platform you play.
2. Install the RomM plugin from Playnite's add-ons browser (search for RomM) or from the
   [releases page](https://github.com/rommapp/playnite-plugin).
3. Open Library, Configure Integrations, RomM. Enter your RomM address without a trailing slash
   and a login, then map each platform to an emulator and a download folder.
4. Choose Library, Import RomM library.

The plugin stores the password in plain text. Use a separate RomM account with the Viewer role.

### Linux and macOS

[ES-DE](https://es-de.org/) runs on Windows, macOS 11 or later, Linux and Android and wraps many
emulators. Its guide has no fixed ROM folder; the examples use `~/ROMs`, and the Create
directories button builds the tree. Its folder names differ from RomM's for some platforms
(`n3ds` where RomM has `3ds`, `dreamcast` where RomM has `dc`), so point ES-DE at a copy or
symlinks, or remap names in RomM instead of renaming the library.

[RetroDECK](https://flathub.org/apps/details/net.retrodeck.retrodeck) is a Flatpak built on
ES-DE. Its default ROM folder is `~/retrodeck/roms/` (from a search snippet of its docs;
unverified).

On macOS, [RetroArch](https://www.retroarch.com/?page=platforms) has a universal build for
macOS 10.13 or later. [OpenEmu](https://github.com/OpenEmu/OpenEmu) was last released in
December 2023 with Intel-only binaries; whether it runs on current macOS is unverified.

## Choose emulators

One suggestion per platform, with the systems each project's own page lists. A blank for Android
means the page does not say.

| Platform | Emulator | Systems |
| --- | --- | --- |
| NES | [Mesen](https://www.mesen.ca/) | Windows, Linux, macOS |
| SNES | [Snes9x](https://github.com/snes9xgit/snes9x) | Windows, Linux, macOS; Android through RetroArch |
| Game Boy, Color, Advance | [mGBA](https://mgba.io/downloads.html) | Windows, Linux, macOS |
| Nintendo DS | [melonDS](https://melonds.kuribo64.net/downloads.php) | Windows, Linux, macOS; Android through RetroArch |
| Nintendo 3DS | [Azahar](https://azahar-emu.org/) | Windows, Linux, macOS, Android |
| GameCube, Wii | [Dolphin](https://github.com/dolphin-emu/dolphin) | Windows, Linux, macOS, Android 7.0+ |
| Nintendo 64 | [RetroArch](https://www.retroarch.com/?page=platforms) with Mupen64Plus-Next | Windows, Linux, macOS, Android |
| Genesis | [RetroArch](https://www.retroarch.com/?page=platforms) with Genesis Plus GX | Windows, Linux, macOS, Android |
| PlayStation | [DuckStation](https://www.duckstation.org/) | Windows, Linux, macOS 13.3+, Android |
| PlayStation 2 | [PCSX2](https://pcsx2.net/) | Windows, Linux, macOS |
| PSP | [PPSSPP](https://www.ppsspp.org/download/) | Windows, Linux, macOS, Android |
| Dreamcast | [Flycast](https://github.com/flyinghead/flycast) | Windows, Linux, macOS, Android |
| Saturn | [Ymir](https://flathub.org/apps/io.github.strikerx3.ymir) | Windows, Linux, macOS (search results only; unverified) |

Azahar continues Citra. Whether Citra is discontinued is unverified here.

### BIOS files

Use BIOS files dumped from consoles you own. romledger does not fetch them, and neither does
this guide.

- DuckStation needs a PS1 or PS2 BIOS in its user directory: `AppData\Local\DuckStation` on
  Windows, `~/.local/share/duckstation` on Linux, `~/Library/Application Support/DuckStation`
  on macOS.
- PCSX2 cannot run games without a BIOS. Where it goes is unverified.
- Sega CD games need Sega CD BIOS files in the front end's system directory
  ([Genesis Plus GX](https://docs.libretro.com/library/genesis_plus_gx/)). A Mega Drive BIOS is
  optional.
- Saturn through the RetroArch Beetle Saturn core needs `sega_101.bin` and `mpr-17933.bin` in
  the system directory ([core docs](https://docs.libretro.com/library/beetle_saturn/)).
- mGBA has a built-in BIOS; an external one is optional.
- In RomM, put BIOS files in `bios/<platform>/`, and upload EmulatorJS BIOS files on the
  platform's Firmware tab.

NES, SNES, N64, GameCube, Wii, 3DS and PSP: no BIOS was named on the pages read.

## Pair a controller

- Windows 11: turn on Bluetooth in Settings, Bluetooth & devices, put the controller in pairing
  mode, and add it under New devices
  ([Microsoft](https://support.microsoft.com/en-us/windows/connect-a-bluetooth-device-in-windows-2be7b51f-6ae9-b757-a3b9-95ee40c3e242)).
- macOS: hold the Xbox button, then hold Connect for a few seconds, and choose the controller in
  Bluetooth settings ([Apple, Xbox](https://support.apple.com/en-us/111101);
  [Apple, PlayStation](https://support.apple.com/en-us/111100)).
- PS5 DualSense: with the controller off, hold Create and the PS button until the light bar
  blinks, then choose it in Bluetooth settings. It works with Windows 10 64-bit and 11, macOS
  11.3 or later, and Android 12 or later
  ([Sony](https://www.playstation.com/en-us/support/hardware/pair-dualsense-controller-bluetooth/)).
- Xbox on Windows and Android: see
  [Xbox's Bluetooth page](https://support.xbox.com/en-US/help/hardware-network/accessories/using-bluetooth-for-xbox-gaming).
  Its steps could not be read when this guide was written.
- Linux and Switch Pro controllers on a PC, Android or Mac: no official instructions were found.
  Your desktop's Bluetooth settings are the starting point.
