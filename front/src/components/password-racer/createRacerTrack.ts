import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export type MovingScenery = {
  mesh: THREE.Object3D;
  factor: number;
  revealAt: number;
  materials: THREE.Material[];
  wrap?: number;
};

/** Shared Blender prefabs keep the rounded circuit scenery to one draw per prop. */
export function createRacerTrack(library: THREE.Group | undefined, low: boolean) {
  const scene = new THREE.Scene();
  const moving: MovingScenery[] = [];
  const usedGeometry = new Set<THREE.BufferGeometry>();
  const vinyl = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: .72, metalness: .025, side: THREE.DoubleSide });

  const animate = (mesh: THREE.Object3D, factor: number, revealAt: number, wrap?: number) => {
    const materials: THREE.Material[] = [];
    mesh.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return;
      const material = (object.material as THREE.Material).clone();
      material.transparent = true; material.opacity = 0;
      object.material = material; materials.push(material);
    });
    moving.push({ mesh, factor, revealAt, materials, wrap });
    scene.add(mesh);
  };
  const prop = (name: string, x: number, z: number, scale: number, factor: number, angle = 0, revealAt = .025) => {
    const template = library?.getObjectByName(name);
    if (!template) return;
    const model = template.clone(true);
    model.position.set(x, -.035, z); model.scale.setScalar(scale); model.rotation.y = angle;
    model.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return;
      usedGeometry.add(object.geometry);
      object.material = vinyl;
    });
    animate(model, factor, revealAt);
  };

  // Rounded trees and landforms move slowly on the far side of the circuit.
  const trees: [string, number, number, number, number, number][] = [
    ['CircuitOak', -5.9, -5.5, 1.10, .16, -.14],
    ['CircuitCypress', -2.8, -6.2, 1.06, .12, .12],
    ['CircuitOak', 1.6, -5.8, .98, .17, .18],
    ['CircuitCypress', 5.0, -6.5, 1.12, .13, -.12],
  ];
  trees.slice(0, low ? 3 : 4).forEach(args => prop(...args));
  const hillGeometry = new THREE.SphereGeometry(1, 24, 12);
  const hillMaterial = new THREE.MeshStandardMaterial({ color: 0x304b3d, roughness: .95 });
  for (const [x, sx] of [[-4.2, 2.8], [3.3, 3.2]]) {
    const hill = new THREE.Mesh(hillGeometry, hillMaterial);
    hill.position.set(x, -.22, -7); hill.scale.set(sx, .66, .5);
    animate(hill, .09, .02);
  }
  hillMaterial.dispose();

  // Mid-distance circuit buildings have seats, shutters, awnings and glazed booths.
  prop('CircuitGrandstand', -4.0, -3.5, 1.05, .35, -.08, .06);
  prop('CircuitPitGarage', .2, -4.2, 1.12, .30, .07, .08);
  prop('CircuitMarshalPost', 4.2, -2.8, 1.02, .45, -.08, .10);
  prop('CircuitRaceBoard', -6.5, -2.2, .90, .53, .03, .10);
  if (!low) prop('CircuitRaceBoard', 6.6, -3.0, .84, .42, -.09, .13);
  prop('CircuitLightTower', -1.6, -4.8, 1.12, .25, .08, .18);
  if (!low) prop('CircuitLightTower', 5.9, -4.8, 1.05, .27, -.08, .18);

  // Chunky molded safety barriers read as rounded miniatures at small sizes.
  prop('CircuitArmco', -5.5, -1.5, 1, .90, .03, .03);
  prop('CircuitTireWall', 1.4, -1.3, 1.05, .96, -.08, .07);
  prop('CircuitArmco', 5.0, -1.6, 1, .90, -.04, .03);

  const road = new THREE.Mesh(new RoundedBoxGeometry(22, .09, 3.6, 2, .04),
    new THREE.MeshStandardMaterial({ color: 0x28353a, roughness: .94 }));
  road.position.set(0, -.115, 0); scene.add(road);
  const grass = new THREE.Mesh(new RoundedBoxGeometry(22, .10, .48, 2, .04),
    new THREE.MeshStandardMaterial({ color: 0x3d5843, roughness: .95 }));
  grass.position.set(0, -.12, -1.94); scene.add(grass);

  // Repeated curb segments and markings share geometry and instanced draw calls.
  const curbGeometry = new RoundedBoxGeometry(.535, .065, .22, 2, .018);
  const matrix = new THREE.Matrix4();
  for (const [color, offset] of [[0xb65d47, 0], [0xaaa78d, .56]]) {
    const material = new THREE.MeshStandardMaterial({ color, roughness: .77 });
    const curbs = new THREE.InstancedMesh(curbGeometry, material, 16);
    for (let i = 0; i < 16; i++) curbs.setMatrixAt(i, matrix.makeTranslation(i * 1.12 - 8.4 + offset, -.052, -1.64));
    animate(curbs, 1.0, .015, 1.12); material.dispose();
  }
  const markingMaterial = new THREE.MeshStandardMaterial({ color: 0x81918a, roughness: .90 });
  const markings = new THREE.InstancedMesh(new RoundedBoxGeometry(.42, .012, .035, 2, .005), markingMaterial, 18);
  for (let i = 0; i < 18; i++) markings.setMatrixAt(i, matrix.makeTranslation(i - 8.5, -.055, 1.2));
  animate(markings, 1.12, .035, 1); markingMaterial.dispose();

  // Soft capsule streaks sit nearest the camera and receive the strongest smear.
  const streakGeometry = new THREE.CapsuleGeometry(.006, .64, 3, 8);
  const streakMaterial = new THREE.MeshBasicMaterial({ color: 0x92b1a6, depthWrite: false });
  for (let i = 0; i < (low ? 3 : 6); i++) {
    const streak = new THREE.Mesh(streakGeometry, streakMaterial);
    streak.rotation.z = Math.PI / 2;
    streak.position.set(-5.5 + i * 1.8, .14 + i % 3 * .34, 2);
    streak.scale.y = .65 + i % 3 * .25;
    animate(streak, 1.65, .38 + i % 2 * .12);
  }
  streakMaterial.dispose(); vinyl.dispose();

  // Prototypes are detached after instancing. Release materials and unused meshes;
  // geometry shared by visible instances is owned by the returned scene.
  const originalMaterials = new Set<THREE.Material>();
  library?.traverse(object => {
    if (!(object instanceof THREE.Mesh)) return;
    if (!usedGeometry.has(object.geometry)) object.geometry.dispose();
    (Array.isArray(object.material) ? object.material : [object.material]).forEach(material => originalMaterials.add(material));
  });
  originalMaterials.forEach(material => material.dispose());
  return { scene, moving };
}
