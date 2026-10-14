# Deploy

Run romledger as a container on a home server, a single-board computer or a workstation, next to
your library. The image bundles Python, Node.js and igir for `linux/amd64` and `linux/arm64`.
Nothing is published to a registry: you build the image yourself, on the host that runs it or on
another machine.

## Requirements

- Docker with Compose and Buildx, on the machine that builds and on the machine that runs.
- A library directory laid out as in [setup.md](setup.md): `roms/<platform>/` and an `inbox/`.
- About 2 GiB of memory for the container. A scan of the NES, PS1, PS2 and GBA DATs peaked near
  1 GiB.

## Build the image

On the machine that will run it, from a checkout of the repository:

```sh
docker build -t romledger:latest .
```

`docker compose up -d --build` (see [Run it](#run-it)) builds it too. To build for another
architecture, name the target platform. Buildx emulates it when it differs from the host, which
is slower than a native build:

```sh
docker buildx build --platform linux/arm64 -t romledger:latest -o type=docker,dest=romledger.tar .
```

- Docker Desktop (macOS, Windows) emulates other architectures out of the box.
- On Linux with Docker Engine, register the emulators once:
  `docker run --privileged --rm tonistiigi/binfmt --install all`.
- Use `linux/arm64` for a Raspberry Pi 4 or 5 and other 64-bit ARM boards, `linux/amd64` for
  most PCs and servers.

## Move the image to another host

If you built elsewhere, copy the archive and load it. A pipe over SSH needs no intermediate file:

```sh
docker save romledger:latest | ssh HOST docker load
```

Or from a file you built with `-o type=docker,dest=romledger.tar`:

```sh
scp romledger.tar HOST:
ssh HOST docker load -i romledger.tar
```

`docker load` prints `Loaded image: romledger:latest`.

## Run it

Work in a checkout, where [compose.yaml](https://github.com/kjiwa/romledger/blob/master/compose.yaml)
lives, or copy that file to the host. Create the config:

```sh
mkdir config data
sudo chown 1000 data
```

Write `config/config.toml` with container paths, as in [setup.md](setup.md):

```toml
[library]
roms = "/library/roms"
inboxes = ["/library/inbox"]

[platforms.nes]
```

Point `ROMLEDGER_LIBRARY` at your library directory (default `./library`) and start it:

```sh
ROMLEDGER_LIBRARY=/mnt/roms docker compose up -d --build
```

`--build` builds the image from the checkout. Without a checkout, load an image as in
[Move the image to another host](#move-the-image-to-another-host) and leave `--build` off.

The port is published on `127.0.0.1` only. To reach the dashboard from other machines on your
network, also set `ROMLEDGER_BIND` to the host's address, or `0.0.0.0` for every interface.

The container runs as user 1000. That user must be able to write `data/` (hence the `chown`), the
`roms/` tree and the inbox. `data/romledger/` holds the DATs, igir's hash cache and `state.db`; keep it on a local disk, not
on the network share.

Read the sign-in link from the log and open it once in a browser. The link names `localhost`; when
you open it from another machine, replace `localhost` with the address you reach the host at:

```sh
docker compose logs romledger
```

The dashboard is plain HTTP; see [Access token](setup.md#access-token) before exposing the port
beyond a network you trust.

Fetch DATs and scan, as on the command line:

```sh
docker compose exec romledger romledger dats update
docker compose exec romledger romledger scan
```

To run a command on a schedule, call it from cron or a systemd timer with `-T`, which disables
the terminal:

```sh
docker compose -f /path/to/compose.yaml exec -T romledger romledger scan
```

## Use it beside RomM

RomM reads the same `roms/<platform>/` folders that `import` fills. Mount the library directory
into RomM's container as its library, following [RomM's documentation](https://docs.romm.app),
and let RomM's scheduled rescan pick up new games; see `hooks.after_import` in
[setup.md](setup.md).

## Update

Pull the new source, then rebuild and recreate the container:

```sh
docker compose up -d --build
```

If you load images instead, load the new one and run `docker compose up -d`.

Compose recreates the container when the `romledger:latest` image has changed. `data/` survives.

## Mount a network share

Mount the share on the host, then bind-mount it into the container. The container sees only the
path you pass in `ROMLEDGER_LIBRARY`.

### Linux, NFS

Add a line to `/etc/fstab` that mounts on first access (`x-systemd.automount`), so a share that is
down at boot does not block it:

```text
server:/export/roms  /mnt/roms  nfs  _netdev,x-systemd.automount,x-systemd.idle-timeout=60  0  0
```

Then run `sudo systemctl daemon-reload && sudo systemctl start mnt-roms.automount` (the unit
name is the mount path with `/` replaced by `-`). Check with `ls /mnt/roms`.

### Linux, SMB

Put the login in a file only root can read, `/etc/romledger-smb`:

```text
username=USER
password=PASSWORD
```

```sh
sudo chmod 600 /etc/romledger-smb
```

Then add to `/etc/fstab`, with the uid and gid of the user the container runs as (1000):

```text
//server/roms  /mnt/roms  cifs  credentials=/etc/romledger-smb,uid=1000,gid=1000,_netdev,x-systemd.automount  0  0
```

`uid` and `gid` set the owner of every file when the server does not report one. If the server
needs a specific protocol version, add `vers=3.0` (or another value from `man mount.cifs`).

### macOS

Mount the share in Finder (Go, Connect to Server, `smb://server/roms`) or with `mount_smbfs`.
It appears under `/Volumes/roms`; pass that path as `ROMLEDGER_LIBRARY`.
