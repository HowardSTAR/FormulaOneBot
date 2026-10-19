import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { damp, racerPhase, speedTargets, type PasswordStrengthLevel } from '../../helpers/passwordRacerState';
import { createRacerTrack } from './createRacerTrack';

type State = { passwordStrengthLevel: PasswordStrengthLevel; isPasswordVisible: boolean };

function studioEnvironment() {
  const studio = new THREE.Scene();
  studio.background = new THREE.Color(.18, .20, .24);
  const panel = (position: THREE.Vector3, width: number, height: number, light: THREE.Color) => {
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), new THREE.MeshBasicMaterial({ color: light, side: THREE.DoubleSide, toneMapped: false }));
    mesh.position.copy(position); mesh.lookAt(0, 0, 0); studio.add(mesh);
  };
  panel(new THREE.Vector3(-3, 5, 5), 5, 5, new THREE.Color(4.5, 4.2, 3.8));
  panel(new THREE.Vector3(4, 3, -3), 3, 5, new THREE.Color(2.1, 2.6, 3.2));
  panel(new THREE.Vector3(4, 1, 6), 4, 3, new THREE.Color(1.2, 1.15, 1.1));
  return studio;
}

/** Batch static geometry by material under each animated pivot, preserving the rig. */
function batchModel(model: THREE.Group) {
  const pivots = new Set(['BodyBounce', 'HeadLift', 'HeadLook', 'VisorPivot', 'EyeExpression', 'EyeBlink', 'EyeGaze',
    'Wheel_Front_L', 'Wheel_Front_R', 'Wheel_Rear_L', 'Wheel_Rear_R']);
  const groups = new Map<THREE.Object3D, Map<THREE.Material, THREE.Mesh[]>>();
  model.updateMatrixWorld(true);
  model.traverse(object => {
    if (!(object instanceof THREE.Mesh) || Array.isArray(object.material)) return;
    let parent = object.parent!;
    while (parent.parent && !pivots.has(parent.name)) parent = parent.parent;
    if (!groups.has(parent)) groups.set(parent, new Map());
    const materials = groups.get(parent)!;
    if (!materials.has(object.material)) materials.set(object.material, []);
    materials.get(object.material)!.push(object);
  });
  const originals = new Set<THREE.BufferGeometry>();
  for (const [parent, materials] of groups) {
    const inverse = parent.matrixWorld.clone().invert();
    for (const [material, meshes] of materials) {
      const geometries = meshes.map(mesh => {
        const geometry = mesh.geometry.clone();
        // Keep baked contact shading; the asset uses no image textures or UVs.
        for (const key of Object.keys(geometry.attributes)) if (!['position', 'normal', 'color'].includes(key)) geometry.deleteAttribute(key);
        geometry.applyMatrix4(new THREE.Matrix4().multiplyMatrices(inverse, mesh.matrixWorld));
        originals.add(mesh.geometry);
        mesh.removeFromParent();
        return geometry;
      });
      const merged = mergeGeometries(geometries);
      geometries.forEach(geometry => geometry.dispose());
      if (merged) parent.add(new THREE.Mesh(merged, material));
    }
  }
  originals.forEach(geometry => geometry.dispose());
}

function disposeScene(scene: THREE.Object3D) {
  const geometries = new Set<THREE.BufferGeometry>();
  const materials = new Set<THREE.Material>();
  scene.traverse(object => {
    if (object instanceof THREE.Mesh) {
      geometries.add(object.geometry);
      (Array.isArray(object.material) ? object.material : [object.material]).forEach(material => materials.add(material));
      if (object instanceof THREE.InstancedMesh) object.dispose();
    }
  });
  geometries.forEach(geometry => geometry.dispose());
  materials.forEach(material => material.dispose());
}

export async function createPasswordRacer(host: HTMLElement, quality: 'auto' | 'low' | 'high', signal: AbortSignal, onUnavailable: () => void = () => {}) {
  const load = async (name: string) => {
    const response = await fetch(`${import.meta.env.BASE_URL}models/password-racer/${name}.glb`, { signal, cache: 'no-cache' });
    if (!response.ok) throw new Error('Racer asset unavailable');
    return new GLTFLoader().parseAsync(await response.arrayBuffer(), '');
  };
  const [racer, circuit] = await Promise.allSettled([load('password-racer'), load('password-racer-track')]);
  if (racer.status === 'rejected') {
    if (circuit.status === 'fulfilled') disposeScene(circuit.value.scene);
    throw racer.reason;
  }
  const gltf = racer.value;
  const trackLibrary = circuit.status === 'fulfilled' ? circuit.value.scene : undefined;
  const model = gltf.scene;
  if (signal.aborted) {
    disposeScene(model); if (trackLibrary) disposeScene(trackLibrary);
    throw new DOMException('Aborted', 'AbortError');
  }
  batchModel(model);
  const low = quality === 'low' || (quality === 'auto' && (navigator.hardwareConcurrency <= 4 || matchMedia('(max-width: 600px)').matches));
  let renderer: THREE.WebGLRenderer;
  try { renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true, powerPreference: 'low-power' }); }
  catch (error) { disposeScene(model); if (trackLibrary) disposeScene(trackLibrary); throw error; }
  renderer.setPixelRatio(Math.min(devicePixelRatio, low ? 1.25 : 1.75));
  renderer.setClearColor(0, 0); renderer.autoClear = false;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = .94;
  renderer.domElement.setAttribute('aria-hidden', 'true');
  host.append(renderer.domElement);

  const foreground = new THREE.Scene(); foreground.add(model);
  // One prefiltered studio map supplies broad softbox reflections for lacquer,
  // metal, rubber and eyes. Contact shading was baked in Blender, so no AO pass.
  const studio = studioEnvironment();
  const pmrem = new THREE.PMREMGenerator(renderer);
  let environment: THREE.WebGLRenderTarget | undefined;
  try {
    environment = pmrem.fromScene(studio, .05, .1, 100, { size: low ? 64 : 128 });
    foreground.environment = environment.texture;
  } catch { /* Direct studio lights still support devices without the HDR target. */ }
  foreground.environmentIntensity = .55;
  disposeScene(studio); pmrem.dispose();
  foreground.add(new THREE.HemisphereLight(0xd5e9ff, 0x494b55, .6));
  const key = new THREE.DirectionalLight(0xffead8, 2.1); key.position.set(-3, 5, 5); foreground.add(key);
  const fill = new THREE.DirectionalLight(0xb5d7ec, 1.35); fill.position.set(4, 3, -3); foreground.add(fill);
  const faceLight = new THREE.DirectionalLight(0xfff1df, .45); faceLight.position.set(0, 2, 6); foreground.add(faceLight);
  const shadow = new THREE.Mesh(new THREE.PlaneGeometry(5.3, .25), new THREE.ShaderMaterial({
    transparent: true, depthWrite: false,
    vertexShader: 'varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader: 'varying vec2 vUv; void main(){vec2 p=(vUv-.5)*2.;float a=exp(-3.5*dot(p,p))*.42;gl_FragColor=vec4(.025,.035,.045,a);}',
  }));
  shadow.position.set(.1, .025, 0); foreground.add(shadow);
  const camera = new THREE.OrthographicCamera(-4, 4, 2, -2, .1, 70);
  // Orthographic side elevation without perspective foreshortening.
  camera.position.set(.08, 1.37, 9); camera.lookAt(.08, 1.37, 0);
  const { scene: background, moving } = createRacerTrack(trackLibrary, low);
  background.environment = foreground.environment;
  background.environmentIntensity = .36;
  background.add(new THREE.HemisphereLight(0xd9e8ec, 0x54604c, 1.0));
  const sceneryKey = new THREE.DirectionalLight(0xffe4c2, 2.0); sceneryKey.position.set(-3, 5, 6); background.add(sceneryKey);
  const sceneryFill = new THREE.DirectionalLight(0xb8d7df, .65); sceneryFill.position.set(4, 2, -3); background.add(sceneryFill);
  host.dataset.scenery = trackLibrary ? 'detailed' : 'track-only';
  const target = new THREE.WebGLRenderTarget(1, 1, { depthBuffer: true });
  const composite = new THREE.Scene();
  const blur = new THREE.ShaderMaterial({
    transparent: true, depthTest: false, depthWrite: false,
    uniforms: { map: { value: target.texture }, amount: { value: 0 } },
    vertexShader: 'varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}',
    // Horizontal motion blur: foreground pixels smear more than distant scenery.
    fragmentShader: `uniform sampler2D map; uniform float amount; varying vec2 vUv;
      void main(){vec4 sum=vec4(0.);float total=0.;
        for(int i=-4;i<=4;i++){float f=float(i);float w=exp(-f*f/7.);
          float depthSmear=mix(.12,1.,pow(1.-vUv.y,2.));
          vec4 c=texture2D(map,vUv+vec2(f*amount*depthSmear,0.));
          sum+=vec4(c.rgb*c.a,c.a)*w;total+=w;}
        float edge=smoothstep(0.,.055,vUv.x)*smoothstep(0.,.055,1.-vUv.x)*smoothstep(0.,.035,vUv.y);
        gl_FragColor=vec4(sum.rgb/max(sum.a,.0001),sum.a/total*.84*edge);
        #include <colorspace_fragment>
      }`,
  });
  composite.add(new THREE.Mesh(new THREE.PlaneGeometry(2, 2), blur));
  const screenCamera = new THREE.Camera();
  const mixer = new THREE.AnimationMixer(model);
  const actions = new Map(gltf.animations.map(clip => [clip.name, mixer.clipAction(clip)]));
  const action = (name: string) => {
    const result = actions.get(name);
    if (!result) throw new Error(`Missing animation: ${name}`);
    return result;
  };
  for (const name of ['idle', 'engine_vibration', 'speed_1', 'start', 'body_tilt', 'head_up', 'visor_open', 'subtle_look']) action(name).play();
  for (const name of ['start', 'body_tilt', 'head_up', 'visor_open', 'subtle_look']) action(name).paused = true;
  const blink = model.getObjectByName('EyeBlink');
  const gaze = model.getObjectByName('EyeGaze');

  let state: State = { passwordStrengthLevel: 0, isPasswordVisible: false };
  let speed = 0, reveal = 0, ignition = 1, faceTime = 0, frame = 0, last = 0, visible = true, disposed = false, unavailable = false;
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const sample = (name: string, progress: number) => { action(name).time = action(name).getClip().duration * Math.min(.9999, Math.max(0, progress)); };
  const render = (delta: number) => {
    speed = reduced.matches ? speedTargets[state.passwordStrengthLevel] : damp(speed, speedTargets[state.passwordStrengthLevel], 2.3, delta);
    if (state.passwordStrengthLevel === 0 && speed < .001) speed = 0;
    reveal = reduced.matches ? Number(state.isPasswordVisible) : damp(reveal, Number(state.isPasswordVisible), 6, delta);
    ignition = Math.min(1, ignition + delta * 2.5);
    action('idle').setEffectiveWeight(1 - speed * .7);
    action('engine_vibration').setEffectiveWeight(speed * .7);
    action('speed_1').setEffectiveTimeScale(reduced.matches ? 0 : speed * 7);
    action('start').setEffectiveWeight(1 - ignition);
    action('body_tilt').setEffectiveWeight(ignition);
    sample('start', ignition); sample('body_tilt', speed);
    sample('head_up', reveal); sample('visor_open', Math.max(0, (reveal - .12) / .88)); sample('subtle_look', reveal);
    mixer.update(reduced.matches ? 0 : delta);
    faceTime = reveal < .05 ? 0 : faceTime + delta;
    if (blink) {
      const blinkPhase = (faceTime + 1.1) % 4.2;
      blink.scale.y = reduced.matches || blinkPhase > .18 ? 1 : 1 - .93 * Math.sin(blinkPhase / .18 * Math.PI);
    }
    if (gaze) gaze.position.set(reduced.matches ? 0 : Math.sin(faceTime * .8) * .012 * reveal, -.012 * reveal, 0);
    for (const item of moving) {
      const opacity = THREE.MathUtils.smoothstep(speed, item.revealAt, item.revealAt + .32);
      item.mesh.visible = opacity > .005;
      item.materials.forEach(material => { material.opacity = opacity; });
      const span = item.wrap ?? 14;
      if (!reduced.matches) item.mesh.position.x = THREE.MathUtils.euclideanModulo(item.mesh.position.x + span / 2 - delta * speed * item.factor * 9, span) - span / 2;
    }
    blur.uniforms.amount.value = reduced.matches ? 0 : Math.pow(speed, 2) * (low ? .007 : .014);
    host.dataset.phase = racerPhase(state.passwordStrengthLevel, ignition < 1);
    host.dataset.speed = speed.toFixed(3);
    host.dataset.reveal = reveal.toFixed(3);
    host.dataset.blur = blur.uniforms.amount.value.toFixed(5);
    renderer.setRenderTarget(target); renderer.clear(); renderer.render(background, camera);
    renderer.setRenderTarget(null); renderer.clear(); renderer.render(composite, screenCamera);
    renderer.clearDepth(); renderer.render(foreground, camera);
  };
  const draw = (delta: number) => {
    if (disposed || unavailable) return;
    try { render(delta); }
    catch { unavailable = true; onUnavailable(); }
  };
  const tick = (now: number) => {
    frame = 0;
    if (disposed || unavailable || !visible || document.hidden || reduced.matches) return;
    const delta = (now - last) / 1000;
    if (delta >= 1 / (low ? 24 : 30)) { last = now; draw(Math.min(delta, .06)); }
    frame = requestAnimationFrame(tick);
  };
  const wake = () => {
    cancelAnimationFrame(frame); frame = 0; last = performance.now();
    if (disposed || unavailable || !visible || document.hidden) return;
    draw(0);
    if (!reduced.matches) frame = requestAnimationFrame(tick);
  };
  const resize = () => {
    const width = host.clientWidth, height = host.clientHeight;
    if (!width || !height) return;
    renderer.setSize(width, height, false);
    const dpr = renderer.getPixelRatio(); target.setSize(Math.round(width * dpr), Math.round(height * dpr));
    const aspect = width / height, halfWidth = Math.max(2.6, aspect * 1.5);
    camera.left = -halfWidth; camera.right = halfWidth; camera.top = halfWidth / aspect; camera.bottom = -halfWidth / aspect; camera.updateProjectionMatrix();
    wake();
  };
  const resizeObserver = new ResizeObserver(resize); resizeObserver.observe(host);
  const intersection = new IntersectionObserver(entries => { visible = entries[0]?.isIntersecting ?? false; wake(); }); intersection.observe(host);
  const lost = (event: Event) => { event.preventDefault(); unavailable = true; cancelAnimationFrame(frame); onUnavailable(); };
  renderer.domElement.addEventListener('webglcontextlost', lost);
  document.addEventListener('visibilitychange', wake); reduced.addEventListener('change', wake);
  resize();

  return {
    update(next: State) {
      if (disposed) return;
      if (state.passwordStrengthLevel === 0 && next.passwordStrengthLevel > 0) ignition = reduced.matches ? 1 : 0;
      state = { passwordStrengthLevel: Math.max(0, Math.min(4, Math.round(next.passwordStrengthLevel))) as PasswordStrengthLevel, isPasswordVisible: Boolean(next.isPasswordVisible) };
      wake();
    },
    dispose() {
      if (disposed) return;
      disposed = true; cancelAnimationFrame(frame);
      resizeObserver.disconnect(); intersection.disconnect();
      document.removeEventListener('visibilitychange', wake); reduced.removeEventListener('change', wake);
      renderer.domElement.removeEventListener('webglcontextlost', lost);
      mixer.stopAllAction(); mixer.uncacheRoot(model);
      disposeScene(foreground); disposeScene(background); disposeScene(composite);
      environment?.dispose();
      target.dispose(); renderer.dispose(); renderer.forceContextLoss(); renderer.domElement.remove();
    },
  };
}
