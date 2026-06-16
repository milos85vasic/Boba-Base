# Releases

Build artefacts per platform / app / version. Everything under this
directory except `README.md` and `.gitkeep` is `.gitignore`d — run
`./scripts/build-releases.sh` to regenerate.

## Layout

```
releases/
├── README.md                             (tracked)
├── .gitkeep                              (tracked)
├── <version>/                            # e.g. 0.1.0, 0.2.0-rc.1
│   ├── frontend/
│   │   ├── debug/                        ng build --configuration=development
│   │   │   ├── frontend-<sha>.tar.gz
│   │   │   └── SHA256SUMS
│   │   ├── release/                      ng build (--configuration=production)
│   │   │   ├── frontend-<sha>.tar.gz
│   │   │   └── SHA256SUMS
│   │   └── BUILD_INFO.json
│   ├── extension/                        BobaLink browser extension (WXT, MV3/MV2)
│   │   ├── debug/                        wxt zip --mode development (Chrome + Firefox)
│   │   │   ├── bobalink-<ver>-chrome-debug.zip
│   │   │   ├── bobalink-<ver>-firefox-debug.zip
│   │   │   ├── bobalink-<ver>-sources-debug.zip
│   │   │   ├── SHA256SUMS
│   │   │   └── BUILD_INFO.json
│   │   └── release/                      wxt zip (Chrome + Firefox + AMO sources)
│   │       ├── bobalink-<ver>-chrome.zip
│   │       ├── bobalink-<ver>-firefox.zip
│   │       ├── bobalink-<ver>-sources.zip
│   │       ├── SHA256SUMS
│   │       └── BUILD_INFO.json
│   ├── download-proxy/                   Python service (no debug/release concept)
│   │   ├── source/
│   │   │   ├── download-proxy-<sha>.tar.gz
│   │   │   └── SHA256SUMS
│   │   ├── container-image/
│   │   │   ├── qbit-download-proxy-<sha>.tar   (podman/docker save)
│   │   │   └── SHA256SUMS
│   │   └── BUILD_INFO.json
│   ├── plugins/                          The 12 canonical plugins, zipped
│   │   ├── plugins-<sha>.zip
│   │   └── SHA256SUMS
│   ├── docs-site/                        mkdocs build output
│   │   ├── site-<sha>.tar.gz
│   │   └── SHA256SUMS
│   └── RELEASE_NOTES.md
└── latest -> <version>/                  (symlink to newest)
```

## Build channels

*  **debug**  — unminified, source-maps, verbose logging. For local
   debugging and dashboards shown in screen-share demos.
*  **release** — production bundle, minified, tree-shaken, hashed
   filenames, no source-maps. Intended for the operator deployment.

The Python services have no distinct "debug/release" concept — the
same bytecode runs with different env flags at runtime. `BUILD_INFO.json`
records the interpreter version, dep hash, and commit SHA for each
container image variant.

## Container-image variants

Built with `podman build`/`docker build` (whichever is auto-detected
per `.specify/memory/constitution.md` Principle IV). Each channel is
tagged:

```
qbit-download-proxy:<version>-debug
qbit-download-proxy:<version>-release
```

and exported with `podman save -o releases/<version>/download-proxy/container-image/...`.

## Provenance

Every artefact ships a matching `SHA256SUMS` file and a `BUILD_INFO.json`:

```json
{
  "artifact": "frontend-<sha>.tar.gz",
  "channel": "release",
  "commit": "<full git sha>",
  "branch": "<branch>",
  "built_at": "<iso-8601 utc>",
  "builder": "<hostname>",
  "toolchain": {"node": "20.x", "angular": "21.x", "python": "3.12.x"}
}
```

## How to build

```bash
./scripts/build-releases.sh                       # all apps, all channels
./scripts/build-releases.sh frontend extension    # both user-facing apps
./scripts/build-releases.sh extension --channel release
```

Targets: `frontend` (Angular dashboard), `extension` (BobaLink, WXT —
Chrome + Firefox zips), `download-proxy`, `plugins`, `docs-site`.

The script is **non-interactive** and exits with `1` on any tool error
(no silent partial releases). `tests/unit/test_releases_script_non_interactive.py`
guards that invariant.
