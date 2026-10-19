import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { damp, estimatePasswordStrength, racerPhase, type PasswordStrengthLevel } from '../src/helpers/passwordRacerState.ts';
import { createRacerTrack } from '../src/components/password-racer/createRacerTrack.ts';

test('local strength estimate respects long Unicode phrases and password policy boundaries', () => {
  const cases: [string, PasswordStrengthLevel][] = [
    ['', 0], ['lap', 1], ['Fast-lap-72!', 2], ['Летний вираж 726', 3],
    ['Летний ветер над тихой рекой 72', 4], ['password1234567890', 1],
    ['12345678901234567890', 1], ['xyzxyzxyzxyzxyzxyzxyz', 1],
    ['д'.repeat(30), 1], ['aB72_' + ' '.repeat(130), 2],
    ['Летний ветер над тихой\nрекой', 2],
  ];
  for (const [password, score] of cases) assert.equal(estimatePasswordStrength(password), score);
});

test('ignition is transient, and all five strength levels have a steady state', () => {
  assert.equal(racerPhase(0, true), 'idle');
  assert.equal(racerPhase(1, true), 'start');
  assert.deepEqual(([0, 1, 2, 3, 4] as const).map(level => racerPhase(level, false)),
    ['idle', 'accelerate_1', 'accelerate_2', 'accelerate_3', 'max_speed']);
});

test('smoothing is independent of frame rate, bounded, and reversible', () => {
  const coarse = damp(0, 1, 4, 1);
  let fine = 0;
  for (let i = 0; i < 60; i++) fine = damp(fine, 1, 4, 1 / 60);
  assert(Math.abs(coarse - fine) < 1e-10);
  assert(damp(fine, 0, 4, .1) < fine);
  assert(damp(fine, 1, 4, .1) <= 1);
});

const bytes = readFileSync(new URL('../public/models/password-racer/password-racer.glb', import.meta.url));
const jsonSize = bytes.readUInt32LE(12);
const manifest = JSON.parse(bytes.subarray(20, 20 + jsonSize).toString('utf8'));

test('detailed Blender asset preserves all clips and fits its web geometry budget', () => {
  assert.equal(bytes.subarray(0, 4).toString(), 'glTF');
  assert.equal(bytes.readUInt32LE(4), 2);
  assert(bytes.length < 3_200_000, 'Detailed mesh and baked shading stay below 3.2 MB');
  const primitives = manifest.meshes.flatMap((mesh: { primitives: { indices: number }[] }) => mesh.primitives);
  const triangles = primitives.reduce((sum: number, primitive: { indices: number }) => sum + manifest.accessors[primitive.indices].count / 3, 0);
  assert(triangles < 90_000, 'No accidental subdivision explosion');
  assert.equal(readFileSync(new URL('../../art/password-racer/password-racer.blend', import.meta.url)).subarray(0, 7).toString(), 'BLENDER');
  const clips = new Set(manifest.animations.map((clip: { name: string }) => clip.name));
  for (const name of ['idle', 'start', 'speed_1', 'speed_2', 'speed_3', 'speed_4', 'head_up', 'head_down', 'visor_open', 'visor_close', 'subtle_look', 'engine_vibration', 'body_tilt', 'victory_boost']) assert(clips.has(name), name);
  assert(!manifest.images?.length, 'No network textures');
  assert(manifest.extensionsUsed.includes('KHR_materials_clearcoat'), 'Lacquer retains its authored clear coat');
  const paint = manifest.materials.find((material: { name: string }) => material.name === 'Coral racing lacquer');
  assert(paint.pbrMetallicRoughness.baseColorFactor[0] > paint.pbrMetallicRoughness.baseColorFactor[1] * 5, 'Export must preserve the coral paint');
  assert(primitives.every((primitive: { attributes: { COLOR_0?: number } }) => primitive.attributes.COLOR_0 !== undefined), 'Baked contact shading must survive export');
});

test('real exported clips lift the head, open the visor, squint, and retain independent wheel motion', async () => {
  const buffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const { scene, animations } = await new GLTFLoader().parseAsync(buffer, '');
  const mixer = new THREE.AnimationMixer(scene);
  const clip = (name: string) => animations.find(animation => animation.name === name)!;
  const head = scene.getObjectByName('HeadLift')!;
  const look = scene.getObjectByName('HeadLook')!;
  const visor = scene.getObjectByName('VisorPivot')!;
  const eyes = scene.getObjectByName('EyeExpression')!;
  const wheel = scene.getObjectByName('Wheel_Front_L')!;
  const restY = head.position.y;
  assert(new THREE.Vector3(0, 0, 1).applyQuaternion(look.quaternion).x > .99, 'Driver faces forward in profile at rest');
  assert(visor.quaternion.angleTo(new THREE.Quaternion()) < 1e-5, 'Default GLB pose has a closed visor');
  const wheelAction = mixer.clipAction(clip('speed_1')).play();
  wheelAction.setEffectiveTimeScale(0);
  for (const name of ['head_up', 'visor_open', 'subtle_look']) {
    const action = mixer.clipAction(clip(name)).play();
    action.paused = true; action.time = clip(name).duration * .9999;
  }
  mixer.update(0);
  assert(head.position.y > restY + .3, 'Head must rise in glTF Y-up coordinates');
  assert(visor.quaternion.angleTo(new THREE.Quaternion()) > 1.3, 'Visor opens about its own pivot');
  assert(eyes.scale.y > .7 && eyes.scale.y < .9, 'Eyes retain a gentle squint on the glTF vertical axis');
  assert(new THREE.Vector3(0, 0, 1).applyQuaternion(look.quaternion).z > .9, 'Driver turns toward the viewer on reveal');
  const blink = scene.getObjectByName('EyeBlink')!;
  const eye = scene.getObjectByName('Eye_-1')!;
  const brow = scene.getObjectByName('Eyebrow_-1')!;
  scene.updateMatrixWorld(true);
  const openEye = eye.getWorldScale(new THREE.Vector3()).y;
  const browScale = brow.getWorldScale(new THREE.Vector3()).y;
  blink.scale.y = .1; scene.updateMatrixWorld(true);
  assert(eye.getWorldScale(new THREE.Vector3()).y < openEye * .2, 'Blink pivot must close the actual eye geometry');
  assert(Math.abs(brow.getWorldScale(new THREE.Vector3()).y - browScale) < 1e-5, 'Blinking must leave the eyebrows independent');
  blink.scale.y = 1;
  const headY = head.position.y, visorPose = visor.quaternion.clone();
  const wheelPose = wheel.quaternion.clone();
  wheelAction.setEffectiveTimeScale(4); mixer.update(.12);
  assert(wheel.quaternion.angleTo(wheelPose) > .2);
  assert.equal(head.position.y, headY);
  assert(visor.quaternion.angleTo(visorPose) < 1e-5);
  for (const name of ['head_up', 'visor_open', 'subtle_look']) mixer.clipAction(clip(name)).time = 0;
  mixer.update(0);
  assert(Math.abs(head.position.y - restY) < 1e-5);
  assert(visor.quaternion.angleTo(new THREE.Quaternion()) < 1e-5);
  mixer.stopAllAction(); mixer.uncacheRoot(scene);
});

test('detailed circuit prefabs keep baked shading, share geometry, and degrade without hiding the road', async () => {
  const trackBytes = readFileSync(new URL('../public/models/password-racer/password-racer-track.glb', import.meta.url));
  assert(trackBytes.length < 1_200_000, 'The nine scenery prefabs stay below 1.2 MB together');
  const jsonSize = trackBytes.readUInt32LE(12);
  const track = JSON.parse(trackBytes.subarray(20, 20 + jsonSize).toString('utf8'));
  assert.equal(track.meshes.length, 9);
  assert.equal(track.materials.length, 1, 'Palette batching avoids a draw per seat, leaf or bolt');
  assert(!track.images?.length, 'No external scenery textures');
  let triangles = 0;
  for (const mesh of track.meshes) {
    assert.equal(mesh.primitives.length, 1);
    const primitive = mesh.primitives[0];
    assert(primitive.attributes.COLOR_0 !== undefined, 'Baked palette/contact shading survives export');
    triangles += track.accessors[primitive.indices].count / 3;
  }
  assert(triangles < 35_000);
  const buffer = trackBytes.buffer.slice(trackBytes.byteOffset, trackBytes.byteOffset + trackBytes.byteLength);
  const library = (await new GLTFLoader().parseAsync(buffer, '')).scene;
  const detailed = createRacerTrack(library, false);
  const low = createRacerTrack(library, true);
  const roadOnly = createRacerTrack(undefined, true);
  assert(low.moving.length < detailed.moving.length, 'Mobile quality reduces instance count, preserving smooth geometry');
  const oaks: THREE.Mesh[] = [];
  detailed.scene.traverse(object => { if (object instanceof THREE.Mesh && object.name === 'CircuitOak_Mesh') oaks.push(object); });
  assert.equal(oaks.length, 2);
  assert.equal(oaks[0].geometry, oaks[1].geometry, 'Repeated scenery shares uploaded geometry');
  assert.notEqual(oaks[0].material, oaks[1].material, 'Instances can fade independently');
  assert(oaks[0].geometry.getAttribute('normal').count > 100, 'Foliage retains its smooth authored surface');
  assert(roadOnly.scene.children.length > 0, 'A failed optional scenery download keeps a usable track');
  const geometry = new Set<THREE.BufferGeometry>(), material = new Set<THREE.Material>();
  for (const result of [detailed, low, roadOnly]) result.scene.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    geometry.add(object.geometry);
    (Array.isArray(object.material) ? object.material : [object.material]).forEach(value => material.add(value));
    if (object instanceof THREE.InstancedMesh) object.dispose();
  });
  geometry.forEach(value => value.dispose()); material.forEach(value => value.dispose());
});
