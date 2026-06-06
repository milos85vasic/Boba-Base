# Jackett update research (2026-06-06)

**Finding:** there is NO Jackett git submodule. Jackett is consumed three ways,
all already current:

1. **Jackett server** — the `lscr.io/linuxserver/jackett:latest` container image
   (which packages github.com/Jackett/Jackett). Pulled to latest this session
   (server build 2026-06-06). New indexer definitions/fixes ship via the image;
   nothing is vendored or built from Jackett source.
2. **qBittorrent jackett.py search plugin** (`plugins/community/jackett.py`) —
   canonical upstream is `qbittorrent/search-plugins` (NOT Jackett/Jackett). Our
   copy is at **parity (v4.9)** plus two local improvements that MUST be
   preserved on any re-sync: (a) JACKETT_API_KEY/JACKETT_URL env overrides in
   `load_configuration()`, (b) the `if not indexers: return` zero-indexers guard
   (BOB-016). Verbatim upstream saved at `upstream_jackett.py.txt` for diffing.
3. **boba-jackett** Go service — our own credential/indexer manager.

**Conclusion:** no source replacement needed; the image is the update vector.
Adding Jackett/Jackett as a submodule (building the .NET server from source)
would be a major architectural change vs. the maintained image — operator
decision, not done unilaterally (§11.4.66/§11.4.122).
