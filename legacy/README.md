# Frozen public interface

`public-frontend.tar.gz` is the exact frontend captured from the running public
web container on 2026-11-01, including the race game, assets and legal pages.
Release identity and checksums are in `release.json`. The archive contains only
public static files, no environment settings or credentials.

Docker extracts it into `front/legacy-dist`. Do not rebuild it from current
sources: the existing public design must stay unchanged during preview.
Develop the new frontend in the root `front/` directory.

See `docs/dual-frontend.md` for rollout and shared-data limitations.
