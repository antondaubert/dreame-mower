# Live video helper

Live video is not part of the integration download. The camera transport needs
a native library that only runs on x86_64 Linux and that we are not in a
position to redistribute, so you build the helper yourself with the script in
this directory. Without it the integration works exactly as before, just
without a camera.

## Requirements

- A Home Assistant host running on **x86_64**. The library is published for no
  other architecture, so Raspberry Pi, Home Assistant Green and Home Assistant
  Yellow cannot run it.
- Docker on that host. The build happens in a throwaway container, so no
  compiler or library is installed on the host itself.
- Network access during the build.

## Installing

On the machine running Home Assistant:

```bash
curl -fsSL https://raw.githubusercontent.com/antondaubert/dreame-mower/main/custom_components/dreame_mower/xp2p/install.sh | bash
```

It finds the Home Assistant containers on that machine that have this
integration installed, builds the helper, and installs it. If it finds
several, it asks which one — or `a` for all of them. If you would rather read
the script first, download it and run it yourself; it takes the same
arguments either way.

The helper sources are taken from the integration it installs into, so the
helper always matches the version you are running.

Then reload the integration: **Settings → Devices & services → Dreame Mower →
⋮ → Reload**. On mowers that support it, the camera appears.

### If Home Assistant is not in Docker

The build needs Docker, so that the host gets no compiler or libraries of its
own. If Home Assistant runs another way on your machine, please open an
[issue](https://github.com/antondaubert/dreame-mower/issues) describing the
setup — we would like to support it. Live video still needs an x86_64 host
either way.

### If discovery misses your instance

Pass the configuration directory — the one holding `configuration.yaml`:

```bash
./install.sh /path/to/homeassistant/config
```

## What it downloads

Only one thing, from its publisher:

| File | Source |
| --- | --- |
| `xp2p_linux.zip` (v2.4.72) | `github.com/tencentyun/iot-p2p-build` releases |

Its SHA-256 is pinned in `build.sh` and checked before anything is compiled.
The build also pulls `ubuntu:24.04` and standard Debian build packages from
their usual repositories.

We ship only `runner.c` and these scripts. The vendor library is fetched by
you, from the vendor, at build time.

## What gets installed

About 8 MB, entirely under `<config>/dreame_mower/xp2p/`:

```
xp2p-runner              the helper, ~200 lines of C plus the vendor library
lib/                     the loader and C runtime it needs
manifest.json            versions and checksums of what was built
```

Nothing is written anywhere else. To uninstall, delete that directory and
reload the integration.

The helper carries its own loader and C library because Home Assistant's
container is built on musl while the vendor library needs glibc. It runs as a
short-lived child process, started when a viewer opens the camera and stopped
when the last one leaves, and it is never linked into Home Assistant itself.

## Rebuilding

Re-run `install.sh`; it replaces the contents of the directory. Do this after
an integration update that changes `runner.c` or the pinned library version —
`manifest.json` records what the current bundle was built from.

## Development note

`install.sh` refuses to build on a non-x86_64 host, because the result would
not run there. On a development machine whose Home Assistant container is an
emulated x86_64, override it:

```bash
DREAME_XP2P_PLATFORM=linux/amd64 ./install.sh ~/dev/homeassistant-dev/config
```

## Interface

The helper reads `key=value` lines on stdin, ending with a blank line, so
credentials never appear in the process list or environment:

```
product_id=   device_name=   p2p_info=   app_id=   app_secret=
quality=      standard | high | super        (optional, default high)
channel=      camera index                   (optional, default 0)
```

It writes one line to stdout — `URL=<local HTTP-FLV address>` or
`ERROR=<reason>` — and holds the session open until stdin closes, so it cannot
outlive the process that started it.
