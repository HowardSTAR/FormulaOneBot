# Modular racing avatars

Created 2026-10-10 using the built-in image_gen tool. Original transparent PNGs are stored in `app-assets.zip` and restored to `app/profile_avatar_assets/` by `python scripts/pack_assets.py --extract`; they depict fictional anonymous racers with no real likenesses, logos or sponsors. The production Pillow renderer registers each bust at the neck seal and independently combines the helmet, suit and five procedural backgrounds. All 45 combinations are available to every account. Subscription profile frames, nickname colors and card backgrounds keep their existing rules.

The public, versioned `/api/profiles/avatar/v1.png` endpoint validates all three identifiers before rendering and caches its finite set of combinations. Selection is saved separately from profile style in `user_profile_avatars` and survives account linking. Shared profile cards capture the saved avatar at creation time; older cards without avatar data use the default.

New visual revisions must use new asset filenames and a new image endpoint version because version 1 responses are immutable.

## Editor performance

The editor composes portraits locally from three lossless WebP atlases in
`front/src/assets/avatar/`. Run `.venv/Scripts/python.exe scripts/build-avatar-sprites.py`
to regenerate them from the same registered source layers. The script verifies all
45 combinations against those layers after encoding. Procedural backgrounds are
flattened to opaque RGB for CSS composition; the immutable PNG renderer for saved
profiles and social cards retains its existing output.

The three atlases total 403,414 bytes and 1,179,648 decoded pixels (about 4.5 MiB
at four bytes per pixel). They cover the entire catalogue, warm during browser idle
time and use hashed build URLs. Once decoded, selection changes only background
positions: there are no combination requests, per-thumbnail loading effects or
image transition layers. Failed initial loading retains the saved portrait and
offers retry. The modal uses an opaque dimmed backdrop and closes immediately.

Run `node scripts/check-avatar-loading.cjs` with Playwright available and
`PROFILE_UI_URL` pointing to a running local frontend. The real-browser regression
checks five viewport sizes, all 45 combinations, 6x CPU slowdown, cold/failed
loading, offline selection, scroll response, stable layout, saving, keyboard focus
and reduced motion. Measurements and screenshots are written to `.tmp/avatar-loading/`.

On 2026-10-12 the production build passed at 320×640, 390×844, 768×1024,
844×390 and 1440×1000 in headless Edge, with 6x CPU throttling and fixture API
responses. Single-click p95 was 34–38 ms (measured through the second animation
frame); scroll-step p95 was 18–21 ms. Selection generated zero image requests.
These are desktop emulation measurements, not physical iOS/Android device results.

## Generation prompts

### scarlet-v1.png

Use case: stylized-concept. Asset: transparent 1024x1024 square racing-driver avatar bust for a modular avatar builder. Premium polished stylized 3D vinyl collectible, physically rendered glossy helmet and matte padded racing suit, soft studio lighting top left, strong dimensional shading. FICTIONAL anonymous racer, no real likeness, no logos, brands, text or numbers. Strict composition: straight frontal camera, symmetrical shoulders, helmet centered at x50%, helmet from y8% to y59%, black neck seal at exactly y60%, shoulder top starts at y63%, wide shoulders fill from x12% to x88% at y78%, torso continues beyond bottom edge. Helmet and shoulders no overlap above y60%. Visor opaque dark smoked glass, no face. Plain transparent background, no floor, no cast shadow outside silhouette. Keep all non-transparent helmet pixels above y60%, torso only below y60%, so upper and lower halves can be combined with other variants. Variant A: scarlet glossy helmet with ivory central stripe, angular black visor with cyan reflection. Scarlet suit with graphite shoulder pads, ivory vertical side stripes, metallic zipper; no gloves or hands visible.

### cobalt-v1.png

Use case: stylized-concept. Asset: transparent 1024x1024 square racing-driver avatar bust for a modular avatar builder. Premium polished stylized 3D vinyl collectible, physically rendered glossy helmet and matte padded racing suit, soft studio lighting top left, strong dimensional shading. FICTIONAL anonymous racer, no real likeness, no logos, brands, text or numbers. Strict composition: straight frontal camera, symmetrical shoulders, helmet centered at x50%, helmet from y8% to y59%, black neck seal at exactly y60%, shoulder top starts at y63%, wide shoulders fill from x12% to x88% at y78%, torso continues beyond bottom edge. Helmet and shoulders no overlap above y60%. Visor opaque dark smoked glass, no face. Plain transparent background, no floor, no cast shadow outside silhouette. Keep all non-transparent helmet pixels above y60%, torso only below y60%, so upper and lower halves can be combined with other variants. Variant B: cobalt blue glossy helmet with two thin electric yellow stripes, angular black visor with cyan reflection. Navy blue suit with cobalt shoulder pads, electric yellow narrow piping, metallic zipper; no gloves or hands visible.

### mint-v1.png

Use case: stylized-concept. Asset: transparent 1024x1024 square racing-driver avatar bust for a modular avatar builder. Premium polished stylized 3D vinyl collectible, physically rendered glossy helmet and matte padded racing suit, soft studio lighting top left, strong dimensional shading. FICTIONAL anonymous racer, no real likeness, no logos, brands, text or numbers. Strict composition: straight frontal camera, symmetrical shoulders, helmet centered at x50%, helmet from y8% to y59%, black neck seal at exactly y60%, shoulder top starts at y63%, wide shoulders fill from x12% to x88% at y78%, torso continues beyond bottom edge. Helmet and shoulders no overlap above y60%. Visor opaque dark smoked glass, no face. Plain transparent background, no floor, no cast shadow outside silhouette. Keep all non-transparent helmet pixels above y60%, torso only below y60%, so upper and lower halves can be combined with other variants. Variant C: pearl white glossy helmet with mint green diagonal trim, angular black visor with cyan reflection. Graphite black suit with mint green shoulder pads, white narrow piping, metallic zipper; no gloves or hands visible.
