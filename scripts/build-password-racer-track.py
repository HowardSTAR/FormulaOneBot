"""Blender 4.5 library of rounded, lightweight circuit scenery for the password racer.

Each named prefab is a single mesh with baked palette/contact shading. Instances
share geometry in Three.js; the layered parallax is controlled by the UI state.
"""
import math
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'art/password-racer'
OUTPUT = ROOT / 'front/public/models/password-racer'
SOURCE.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.context.preferences.filepaths.save_version = 0

PALETTE = {
    'leaf': (.13, .31, .19), 'leaf_light': (.22, .43, .25), 'leaf_dark': (.07, .21, .14),
    'bark': (.21, .12, .075), 'teal': (.10, .25, .27), 'teal_light': (.20, .39, .40),
    'ivory': (.79, .77, .63), 'coral': (.65, .15, .07), 'glass': (.055, .13, .17),
    'metal': (.30, .37, .38), 'rubber': (.026, .037, .043), 'stone': (.25, .29, .27),
    'lamp': (.91, .66, .25), 'white': (.86, .88, .79),
}
materials = {}
for name, color in PALETTE.items():
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    materials[name] = mat

library = bpy.data.objects.new('CircuitLibrary', None)
bpy.context.collection.objects.link(library)
prefabs = []
current = None


def prefab(name):
    global current
    current = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(current)
    current.parent = library
    current.location.x = len(prefabs) * 6
    current['role'] = 'Reusable rounded circuit scenery; one batched mesh per instance.'
    prefabs.append(current)
    return current


def finish(obj, name, loc, color, smooth=True):
    obj.name = name
    obj.parent = current
    obj.location = loc
    obj.data.materials.append(materials[color])
    for face in obj.data.polygons:
        face.use_smooth = smooth
    return obj


def box(name, loc, size, color, radius=.04):
    bpy.ops.mesh.primitive_cube_add(size=1)
    obj = finish(bpy.context.object, name, loc, color)
    obj.scale = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel = obj.modifiers.new('Rounded corners', 'BEVEL')
    bevel.width, bevel.segments = min(radius, min(size) * .42), 3
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    normals = obj.modifiers.new('Soft weighted normals', 'WEIGHTED_NORMAL')
    bpy.ops.object.modifier_apply(modifier=normals.name)
    return obj


def sphere(name, loc, size, color, segments=20, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings)
    obj = finish(bpy.context.object, name, loc, color)
    obj.scale = size
    return obj


def rod(name, start, end, radius, color, vertices=12):
    start, end = Vector(start), Vector(end)
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=(end - start).length)
    obj = finish(bpy.context.object, name, (start + end) / 2, color)
    obj.rotation_euler = (end - start).to_track_quat('Z', 'Y').to_euler()
    bevel = obj.modifiers.new('Rounded ends', 'BEVEL')
    bevel.width, bevel.segments = radius * .3, 2
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    return obj


def panel(name, verts, faces, color):
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return finish(obj, name, (0, 0, 0), color)


def flag(x, y, height, color, checker=False):
    rod('Flagpole', (x, y, .04), (x, y, height + .08), .018, 'metal')
    sphere('Flagpole cap', (x, y, height + .09), (.028, .028, .028), 'lamp', 12, 8)
    verts = []
    for row in range(4):
        for col in range(7):
            t = col / 6
            verts.append((x + t * .48, y + math.sin(t * math.tau - row * .24) * .043,
                          height - row * .09 - t * .07))
    for row in range(3):
        for col in range(6):
            a = row * 7 + col
            cell_color = ('white' if (col + row) % 2 else 'glass') if checker else color
            panel('Woven flag', [verts[i] for i in [a, a + 1, a + 8, a + 7]], [(0, 1, 2, 3)], cell_color)


prefab('CircuitOak')
rod('Tapered trunk', (0, 0, .02), (.045, 0, 1.2), .075, 'bark', 16)
for end in [(-.34, -.04, 1.36), (.36, .08, 1.50), (.08, -.12, 1.71)]:
    rod('Curved bough', (.02, 0, .73), end, .035, 'bark')
for loc, size, color in [
    ((-.32, .03, 1.30), (.44, .36, .40), 'leaf_dark'),
    ((.30, .04, 1.45), (.46, .37, .43), 'leaf'),
    ((-.12, .08, 1.78), (.44, .37, .43), 'leaf_light'),
    ((-.03, -.22, 1.47), (.44, .34, .43), 'leaf'),
    ((.24, -.14, 1.72), (.30, .28, .32), 'leaf_light'),
]:
    sphere('Soft foliage crown', loc, size, color)
for x, y in [(-.18, .05), (.15, -.09), (.02, .16)]:
    sphere('Rounded root stone', (x, y, .04), (.12, .1, .055), 'stone', 12, 8)

prefab('CircuitCypress')
rod('Tree trunk', (0, 0, .02), (0, 0, 1.54), .049, 'bark', 16)
for i, (z, width, height) in enumerate([(.76, .34, .51), (1.18, .28, .48), (1.58, .21, .42)]):
    sphere('Sculpted evergreen', (.02 * (-1) ** i, 0, z), (width, width * .83, height),
           'leaf' if i % 2 else 'leaf_dark', 20, 14)

prefab('CircuitGrandstand')
box('Concrete foundation', (0, .16, .10), (1.95, .90, .20), 'stone', .06)
for row in range(3):
    z, y = .25 + row * .20, -.16 + row * .25
    box('Terrace', (0, y, z), (1.83, .32, .12), 'ivory', .025)
    for seat in range(7):
        x = -.76 + seat * .25
        color = ['teal', 'coral', 'teal_light', 'ivory'][(seat + row) % 4]
        box('Molded seat cushion', (x, y - .025, z + .10), (.18, .18, .048), color, .022)
        back = box('Rounded seat back', (x, y + .067, z + .20), (.18, .045, .20), color, .028)
        back.rotation_euler.x = -.12
for x in [-.90, .90]:
    rod('Roof upright', (x, .40, .12), (x, .40, 1.48), .032, 'metal')
    rod('Roof brace', (x, .4, .86), (x, -.25, 1.37), .022, 'metal')
    rod('Safety rail', (x, -.41, .38), (x, -.41, .76), .014, 'metal')
rod('Front safety rail', (-.91, -.41, .76), (.91, -.41, .76), .019, 'metal')
roof = box('Overhanging canopy', (0, .05, 1.46), (2.18, 1.18, .12), 'teal', .05)
roof.rotation_euler.x = -.06
box('Canopy ivory fascia', (0, -.54, 1.42), (2.12, .065, .13), 'ivory', .025)
box('Canopy coral stripe', (0, -.578, 1.43), (1.62, .012, .035), 'coral', .005)

prefab('CircuitPitGarage')
box('Garage building', (0, .1, .49), (1.90, .72, .95), 'ivory', .07)
box('Dark glazing surround', (0, -.274, .54), (1.70, .025, .68), 'teal', .026)
for x in [-.54, 0, .54]:
    box('Garage shutter', (x, -.298, .39), (.46, .025, .43), 'metal', .012)
    for row in range(5):
        box('Shutter slat', (x, -.318, .22 + row * .075), (.43, .012, .018), 'stone', .005)
    box('Tinted upper window', (x, -.3, .75), (.46, .028, .19), 'glass', .012)
    box('Window glint', (x - .13, -.319, .77), (.022, .005, .14), 'teal_light', .002)
box('Roof cap', (0, .09, 1.01), (2.04, .86, .13), 'teal', .045)
awning = box('Pit lane awning', (0, -.36, .93), (1.90, .43, .07), 'coral', .025)
awning.rotation_euler.x = .10
for x in [-.87, .87]:
    rod('Awning support', (x, -.51, .91), (x, -.51, .04), .022, 'metal')
flag(-.62, .1, 1.60, 'coral')

prefab('CircuitRaceBoard')
for x in [-.50, .50]:
    box('Sign base', (x, 0, .055), (.29, .30, .11), 'stone', .035)
    rod('Board upright', (x, 0, .07), (x, 0, .88), .024, 'metal')
box('Rounded board frame', (0, 0, 1.02), (1.46, .11, .58), 'ivory', .075)
box('Board teal face', (0, -.065, 1.02), (1.34, .018, .46), 'teal', .04)
for i in range(3):
    bar = box('Racing chevron', (-.38 + i * .32, -.08, 1.03), (.10, .014, .27),
              'coral' if i == 0 else 'ivory', .018)
    bar.rotation_euler.y = .38

prefab('CircuitArmco')
for x in [-.94, -.31, .31, .94]:
    box('Galvanized post', (x, .05, .28), (.07, .10, .55), 'metal', .02)
    box('Post footing', (x, .05, .035), (.20, .21, .07), 'stone', .02)
for z in [.20, .38]:
    box('Rounded crash rail', (0, -.04, z), (2.12, .13, .12), 'metal', .04)
    for x in [-.94, -.31, .31, .94]:
        sphere('Rail bolt', (x, -.113, z), (.018, .009, .018), 'ivory', 10, 6)
for x in [-1.05, 1.05]:
    box('Coral reflector', (x, -.12, .38), (.09, .012, .09), 'coral', .02)

prefab('CircuitTireWall')
box('Tire wall footing', (0, .03, .035), (1.30, .45, .07), 'stone', .03)
for row in range(2):
    for col in range(4):
        bpy.ops.mesh.primitive_torus_add(major_radius=.125, minor_radius=.049,
                                       major_segments=20, minor_segments=8)
        obj = finish(bpy.context.object, 'Rounded safety tire', (-.47 + col * .31, 0, .15 + row * .20),
                     'coral' if col == 0 else 'rubber')
        obj.scale.z = 1.40
for x in [-.65, .65]:
    rod('Wall strap', (x, .02, .02), (x, .02, .48), .018, 'metal')

prefab('CircuitMarshalPost')
box('Marshal pedestal', (0, 0, .10), (.56, .50, .20), 'stone', .04)
box('Rounded marshal booth', (0, .03, .69), (.55, .45, .98), 'ivory', .065)
box('Tinted booth window', (0, -.204, .88), (.43, .024, .31), 'glass', .025)
box('Window divider', (0, -.224, .88), (.022, .012, .31), 'ivory', .004)
box('Booth roof', (0, .01, 1.22), (.72, .66, .13), 'teal', .045)
box('Marshal warning panel', (0, -.213, .46), (.27, .025, .16), 'coral', .02)
flag(.40, .04, 1.65, 'coral', checker=True)

prefab('CircuitLightTower')
box('Light base', (0, 0, .06), (.28, .29, .12), 'stone', .03)
rod('Light mast', (0, 0, .1), (0, 0, 1.85), .027, 'metal', 16)
rod('Light crossbar', (-.34, 0, 1.81), (.34, 0, 1.81), .025, 'metal')
for x in [-.26, 0, .26]:
    box('Floodlight housing', (x, -.02, 1.85), (.22, .16, .18), 'teal', .035)
    box('Warm light lens', (x, -.108, 1.85), (.16, .018, .12), 'lamp', .02)

# Bake the palette and local contact shading, then batch each prefab to one draw.
bpy.context.view_layer.update()
meshes = [obj for prop in prefabs for obj in prop.children if obj.type == 'MESH']
verts, faces = [], []
for obj in meshes:
    start = len(verts)
    verts.extend(obj.matrix_world @ vertex.co for vertex in obj.data.vertices)
    faces.extend(tuple(start + i for i in face.vertices) for face in obj.data.polygons)
bvh = BVHTree.FromPolygons(verts, faces)
palette_material = bpy.data.materials.new('Circuit painted vinyl')
palette_material.diffuse_color = (1, 1, 1, 1)
palette_material.use_nodes = True
shader = palette_material.node_tree.nodes.get('Principled BSDF')
shader.inputs['Base Color'].default_value = (1, 1, 1, 1)
shader.inputs['Roughness'].default_value = .67
shader.inputs['Coat Weight'].default_value = .10
attribute = palette_material.node_tree.nodes.new('ShaderNodeVertexColor')
attribute.layer_name = 'CircuitPalette'
palette_material.node_tree.links.new(attribute.outputs['Color'], shader.inputs['Base Color'])
for obj in meshes:
    color = obj.data.materials[0].diffuse_color
    attribute = obj.data.color_attributes.new(name='CircuitPalette', type='BYTE_COLOR', domain='POINT')
    normals = obj.matrix_world.inverted_safe().transposed().to_3x3()
    for vertex, value in zip(obj.data.vertices, attribute.data):
        normal = (normals @ vertex.normal).normalized()
        origin = obj.matrix_world @ vertex.co + normal * .004
        axis = Vector((0, 0, 1)) if abs(normal.z) < .9 else Vector((1, 0, 0))
        tangent = normal.cross(axis).normalized()
        blocked = 0
        for direction in [normal, normal * .7 + tangent * .7, normal * .7 - tangent * .7]:
            hit, _, _, distance = bvh.ray_cast(origin, direction.normalized(), .20)
            if hit is not None:
                blocked += (1 - distance / .20) / 3
        ao = 1 - .30 * blocked
        value.color = (color[0] * ao, color[1] * ao, color[2] * ao, 1)
    obj.data.materials.clear()
    obj.data.materials.append(palette_material)

for prop in prefabs:
    bpy.ops.object.select_all(action='DESELECT')
    parts = list(prop.children)
    for obj in parts:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = parts[0]
    bpy.ops.object.join()
    merged = bpy.context.object
    merged.name = prop.name + '_Mesh'
    # Keep the shared instance origin at ground level, independent of first part.
    bpy.context.scene.cursor.location = prop.matrix_world.translation
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

library['description'] = 'Smooth circuit miniatures with baked palette and contact shading.'
bpy.context.scene.world.color = (.18, .18, .18)
bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / 'password-racer-track.blend'))
bpy.ops.object.select_all(action='SELECT')
bpy.ops.export_scene.gltf(filepath=str(OUTPUT / 'password-racer-track.glb'), export_format='GLB',
                         export_animations=False, export_cameras=False, export_lights=False,
                         export_extras=True, use_selection=True)
print('PASSWORD_RACER_TRACK_EXPORTED', OUTPUT / 'password-racer-track.glb', flush=True)
