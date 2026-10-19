# Password racer

Original stylized asset authored with Blender 4.5 LTS. `password-racer.blend` is the editable source; `front/public/models/password-racer/password-racer.glb` is the detailed web export (about 2.7 MB, 80,000 triangles, 14 clips, no image textures). Geometry, materials and baked contact shading are batched under animated pivots when loaded. The compact monocoque, undercut sidepods, layered airfoils and oversized slicks follow the supplied cartoon F1 references. The collectible driver has a rounded-square vinyl face, black domed eyes, tiny nose, curved brows and a coral race suit with ivory harnesses and glove details. The full-face ivory racing helmet has a rounded cranial dome, projecting chin bar, rubber eyeport seals, vents and a curved smoked visor fitted to the shell. The visor rotates around separate temple hinges, independently of the head. The car includes original livery, tire lettering, drilled brake discs, fixed calipers, suspension links, panel seams, cooling louvres and wing hardware.

Rebuild from the repository root:

```powershell
.tools\blender\blender-4.5.9-windows-x64\blender.exe --background --factory-startup --python-exit-code 1 --python scripts/build-password-racer.py
.tools\blender\blender-4.5.9-windows-x64\blender.exe --background --factory-startup --python-exit-code 1 --python scripts/build-password-racer-track.py
```

Blender is a portable, SHA-256-verified download in the ignored `.tools` directory. Another Blender 4.5 installation can run the same script. The builder raycasts local contact occlusion into vertex colors and exports lacquer through `KHR_materials_clearcoat`. Lettering uses Arial Black when installed, with Blender's built-in font as fallback; glyphs are converted to geometry. No font or image download is required at runtime. The builder also renders `poster.webp` and a larger `detail-reveal.webp` for visual inspection. Model forward is Blender +X, audience -Y, up +Z; glTF export converts to Y-up. Wheel pivots use Blender Y, visor uses local X, head lift uses Z. Parts remain separate and editable in the source file. Named NLA tracks export as named glTF clips.

`password-racer-track.blend` contains nine original circuit prefabs: a broadleaf tree, cypress, grandstand, pit garage, race board, Armco barrier, tire wall, marshal post and light tower. Foliage has smooth rounded crowns; buildings have beveled edges, molded seats, canopy supports, glazing and shutter slats; safety details include bolts, reflectors and curved woven flags. Their palette and contact shading are baked to vertex colors. Each prefab exports as one mesh/one material, totaling about 1.1 MB and 32,300 triangles in `password-racer-track.glb`. Repeated props share geometry; curb segments and road markings use instancing. Missing scenery keeps the car and the road usable.

## Integration

```tsx
<PasswordField racer label="Пароль" value={password}
  onChange={event => setPassword(event.target.value)} />

// Standalone: only derived state crosses the scene boundary.
<PasswordRacer passwordStrengthLevel={3} isPasswordVisible={false} quality="auto" />
```

Five scores map to `idle`, `accelerate_1`, `accelerate_2`, `accelerate_3`, `max_speed`; `start` is a 400 ms ignition transition. `AnimationMixer` samples independently authored `head_up`, `visor_open`, `subtle_look`, and `body_tilt` clips. Sampling reveal in both directions makes fast show/hide reversals continuous; `head_down` and `visor_close` are also available for one-shot integrations. The mixer plays `speed_1` with continuously adjusted time scale and blends idle/vibration. All four speed clips and optional victory boost are included in the GLB.

The fixed orthographic camera shows the car strictly in profile. On reveal, the driver lifts and turns toward the viewer, opens the visor, and looks down toward the input. There are no visible stages, score bars, counters, lights or changing captions. Speed follows the input through exponential smoothing; scenery fades in with continuous speed rather than switching on at score boundaries. Soft studio lighting gives the circuit miniatures volume. Slow trees and rolling hills, medium-speed circuit buildings, and faster barriers, curbs and capsule streaks create layered parallax. The car stays sharp over one background render target with a nine-tap horizontal blur. Blur increases continuously with speed; the distant upper scenery stays more legible than the near ground. The scenery edges fade into the surrounding page. Strength is a local, conservative length/pattern estimate, not a breach check or a guarantee; backend validation is authoritative and long phrases in Cyrillic are supported.

Three.js is dynamically imported only near the viewport. Three procedural studio softboxes produce a small PMREM reflection map (64 pixels per cube face on low quality, 128 on high); no external HDR is fetched. Rendering stops offscreen and in hidden tabs. Auto quality limits small/low-core devices to 24 FPS, DPR 1.25, fewer instances and less blur while preserving smooth scenery geometry; high quality caps DPR at 1.75 and 30 FPS. Antialiasing remains enabled for legible small details. `quality="low"` explicitly reduces effects. Independent blink and gaze pivots animate only the eyes during reveal. Reduced motion renders only on state/size changes with no blur, blinking or scanning. A transparent WebP rendered by Blender remains usable when WebGL or the racer GLB is unavailable. Unmount aborts loading and releases observers, animation actions, geometry, instance buffers, materials, render targets, studio reflections and the WebGL context. The scene never receives, stores or transmits the password. Asset checks enforce a 3.2 MB/90,000-triangle car budget and a separate 1.2 MB/35,000-triangle scenery budget.

## Verification

```powershell
cd front
node --experimental-strip-types --test tests/password-racer.test.ts
node node_modules/typescript/bin/tsc -b
node node_modules/vite/bin/vite.js build
# Start Vite on 127.0.0.1:5176, then from repository root:
node scripts/check-password-racer.cjs
```

References: [Blender glTF export](https://docs.blender.org/manual/en/4.5/addons/import_export/scene_gltf2.html), [Three.js animation system](https://threejs.org/manual/pages/animation-system.html), [WebGLRenderer](https://threejs.org/docs/pages/WebGLRenderer.html).
