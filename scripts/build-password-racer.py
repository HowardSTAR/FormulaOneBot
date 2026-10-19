"""Reproducible Blender 4.5 LTS asset. Run with blender --background --python this_file.

Coordinates in Blender: +X forward, -Y audience, +Z up. Export is glTF Y-up.
Every moving part has its own transform pivot. No third-party models or textures.
"""
import json
import math
import struct
from pathlib import Path

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'art/password-racer'
OUTPUT = ROOT / 'front/public/models/password-racer'
SOURCE.mkdir(parents=True, exist_ok=True)
OUTPUT.mkdir(parents=True, exist_ok=True)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene = bpy.context.scene
bpy.context.preferences.filepaths.save_version = 0
scene.render.fps = 30
scene.frame_start, scene.frame_end = 1, 61


def material(name, color, roughness=.42, metallic=0, coat=0):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (*color, 1)
    shader.inputs['Roughness'].default_value = roughness
    shader.inputs['Metallic'].default_value = metallic
    shader.inputs['Coat Weight'].default_value = coat
    if coat:
        shader.inputs['Coat Roughness'].default_value = .2
    return mat


red = material('Coral racing lacquer', (.72, .048, .022), .3, .18, .7)
dark = material('Satin carbon', (.024, .03, .039), .43, .12)
helmet_mat = material('Ivory helmet vinyl', (.91, .87, .73), .4, 0, .3)
rubber = material('Soft slick rubber', (.019, .023, .029), .82)
rim = material('Forged titanium wheels', (.22, .27, .31), .33, .72)
cream = material('Warm ivory', (.98, .93, .78))
skin = material('Warm tan face', (.74, .47, .29), .7)
visor_mat = material('Smoked visor', (.019, .039, .052), .22, .16, .55)
eye_mat = material('Black vinyl eyes', (.005, .007, .009), .3, 0, .25)
iris_mat = material('Chestnut irises', (.14, .065, .023), .36, 0, .3)
white = material('Warm eye whites', (.96, .96, .9), .31)
fabric = material('Coral race suit', (.53, .032, .022), .78)
bronze = material('Champagne anodized hardware', (.62, .38, .13), .36, .72)
seam = material('Recessed panel seams', (.009, .015, .022), .7)
tire_ink = material('Tire sidewall lettering', (.63, .65, .54), .85)
glass_edge = material('Glass polished edge', (.15, .29, .34), .26, .3)


def empty(name, loc=(0, 0, 0), parent=None):
    obj = bpy.data.objects.new(name, None)
    scene.collection.objects.link(obj)
    obj.parent = parent
    obj.location = loc
    obj.empty_display_size = .2
    return obj


root = empty('Racer')
tilt = empty('BodyTilt', parent=root)
bounce = empty('BodyBounce', parent=tilt)


def finish(obj, name, loc, scale, mat, parent):
    obj.name = name
    obj.parent = parent
    obj.location = loc
    obj.scale = scale
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return obj


def sphere(name, loc, scale, mat, parent=bounce, segments=24, rings=12):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segments, ring_count=rings)
    return finish(bpy.context.object, name, loc, scale, mat, parent)


def box(name, loc, scale, mat, parent=bounce, bevel=.12):
    bpy.ops.mesh.primitive_cube_add(size=2)
    obj = finish(bpy.context.object, name, loc, scale, mat, parent)
    # Bake scale before bevel so corners keep a consistent radius.
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        modifier = obj.modifiers.new('Soft toy corners', 'BEVEL')
        modifier.width, modifier.segments = bevel, 3
        bpy.ops.object.modifier_apply(modifier=modifier.name)
        normal = obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
        bpy.ops.object.modifier_apply(modifier=normal.name)
    return obj


def cylinder(name, loc, radius, depth, mat, parent=bounce, rotation=(0, 0, 0), vertices=24):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth)
    obj = finish(bpy.context.object, name, loc, (1, 1, 1), mat, parent)
    obj.rotation_euler = rotation
    bevel = obj.modifiers.new('Round edges', 'BEVEL')
    bevel.width, bevel.segments = .035, 2
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    return obj


def rod(name, start, end, radius, mat, parent=bounce):
    start, end = Vector(start), Vector(end)
    obj = cylinder(name, (start + end) / 2, radius, (end - start).length, mat, parent, vertices=12)
    obj.rotation_euler = (end - start).to_track_quat('Z', 'Y').to_euler()
    return obj


def stroke(name, points, radius, mat, parent=bounce, resolution=8):
    curve = bpy.data.curves.new(name, 'CURVE')
    curve.dimensions, curve.resolution_u = '3D', resolution
    curve.bevel_depth, curve.bevel_resolution = radius, 1
    spline = curve.splines.new('BEZIER')
    spline.bezier_points.add(len(points) - 1)
    for point, co in zip(spline.bezier_points, points):
        point.co = co
        point.handle_left_type = point.handle_right_type = 'AUTO'
    obj = bpy.data.objects.new(name, curve)
    scene.collection.objects.link(obj)
    obj.parent = parent
    obj.data.materials.append(mat)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    return bpy.context.object


font_path = Path('C:/Windows/Fonts/ariblk.ttf')
font = bpy.data.fonts.load(str(font_path)) if font_path.exists() else bpy.data.fonts.get('Bfont')


def lettering(name, value, loc, size, mat, parent, side=-1, angle=0):
    curve = bpy.data.curves.new(name, 'FONT')
    curve.body, curve.size = value, size
    curve.align_x, curve.align_y = 'CENTER', 'CENTER'
    curve.font, curve.resolution_u = font, 3
    obj = bpy.data.objects.new(name, curve)
    scene.collection.objects.link(obj)
    obj.parent, obj.location = parent, loc
    basis = Matrix(((-side, 0, 0), (0, 0, side), (0, 1, 0)))
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = Quaternion((0, 1, 0), angle) @ basis.to_quaternion()
    obj.data.materials.append(mat)
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target='MESH')
    return bpy.context.object


def mesh_object(name, verts, faces, mat, parent=bounce):
    mesh = bpy.data.meshes.new(name + '_mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    scene.collection.objects.link(obj)
    return finish(obj, name, (0, 0, 0), (1, 1, 1), mat, parent)


def loft(name, sections, mat, offset_y=0, parent=bounce, subdivision=1):
    """Quad surface: longitudinal stations with elliptical cross sections."""
    verts, faces, count = [], [], 16
    for x, width, bottom, top in sections:
        for i in range(count):
            angle = math.tau * i / count
            verts.append((x, offset_y + width * math.cos(angle),
                          (top + bottom) / 2 + (top - bottom) / 2 * math.sin(angle)))
    for j in range(len(sections) - 1):
        for i in range(count):
            a, b = j * count + i, j * count + (i + 1) % count
            faces.append((a, b, b + count, a + count))
    faces += [tuple(reversed(range(count))), tuple((len(sections) - 1) * count + i for i in range(count))]
    obj = mesh_object(name, verts, faces, mat, parent)
    if subdivision:
        mod = obj.modifiers.new('Flowing surface', 'SUBSURF')
        mod.levels = subdivision
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.modifier_apply(modifier=mod.name)
    return obj


def side_panel(name, outline, y, mat, thickness=.035, rounding=.035):
    # Round the silhouette itself; a bevel limited by plate thickness cannot do it.
    rounded = []
    for index, point in enumerate(outline):
        prev, current, after = Vector(outline[index - 1]), Vector(point), Vector(outline[(index + 1) % len(outline)])
        radius = min(rounding, (prev - current).length * .24, (after - current).length * .24)
        start = current + (prev - current).normalized() * radius
        end = current + (after - current).normalized() * radius
        rounded.extend(tuple((1 - t) ** 2 * start + 2 * (1 - t) * t * current + t ** 2 * end)
                       for t in [i / 4 for i in range(5)])
    outline = rounded
    verts = [(x, y + d, z) for d in [-thickness / 2, thickness / 2] for x, z in outline]
    n = len(outline)
    faces = [tuple(reversed(range(n))), tuple(range(n, n * 2))]
    faces += [(i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)]
    obj = mesh_object(name, verts, faces, mat)
    mod = obj.modifiers.new('Rounded plate edges', 'BEVEL')
    mod.width, mod.segments = .025, 2
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=mod.name)
    normal = obj.modifiers.new('Panel normals', 'WEIGHTED_NORMAL')
    bpy.ops.object.modifier_apply(modifier=normal.name)
    return obj


def wing(name, x, z, span, chord, mat):
    verts, faces = [], []
    # Closed cambered airfoil, swept upward gently toward the endplates.
    profile = [(t, .035 * math.sin(math.pi * t) + side * .018 * math.sin(math.pi * t) ** .7)
               for side, steps in [(1, range(9)), (-1, range(7, 0, -1))] for t in [i / 8 for i in steps]]
    for y in [-span, -.7 * span, 0, .7 * span, span]:
        edge = (abs(y) / span) ** 2
        for t, h in profile:
            verts.append((x + (t - .5) * chord + edge * .13, y, z + h + edge * .045))
    n = len(profile)
    for j in range(4):
        for i in range(n):
            a, b = j * n + i, j * n + (i + 1) % n
            faces.append((a, b, b + n, a + n))
    faces += [tuple(reversed(range(n))), tuple(4 * n + i for i in range(n))]
    return mesh_object(name, verts, faces, mat)


# Contemporary F1 silhouette: tapered monocoque, undercut sidepods and aerofoils.
loft('Monocoque', [(-1.75, .1, .4, .66), (-1.45, .28, .34, .87), (-.95, .43, .31, .96),
                   (-.4, .43, .3, .89), (.2, .32, .29, .82), (.7, .23, .27, .7),
                   (1.3, .16, .25, .54), (2, .1, .24, .38), (2.37, .035, .27, .32)], red)
box('Carbon_floor', (-.16, 0, .24), (1.76, .89, .035), dark, bevel=.035)
loft('Engine_cover', [(-1.7, .06, .48, .7), (-1.35, .19, .5, 1.12), (-.95, .24, .57, 1.28),
                      (-.8, .15, .75, 1.32)], red)
for side in [-1, 1]:
    loft('Sidepod_' + str(side), [(-1.48, .08, .35, .47), (-1.18, .24, .3, .57),
         (-.6, .34, .31, .73), (.08, .35, .38, .79), (.42, .24, .43, .74), (.47, .18, .46, .66)], red, side * .55)
    sphere('Sidepod_intake_' + str(side), (.4, side * .59, .65), (.025, .19, .082), dark)
    side_panel('Sidepod_pinstripe_' + str(side), [(-1.18, .38), (-.65, .43), (.19, .57), (.26, .6), (-.65, .47)], side * .875, cream, .008)
    rod('Mirror_stalk_' + str(side), (.18, side * .33, .76), (.2, side * .65, .94), .018, dark)
    sphere('Mirror_' + str(side), (.21, side * .67, .96), (.12, .06, .045), red)
    side_panel('Front_endplate_' + str(side), [(1.79, .18), (2.52, .18), (2.49, .48), (2.35, .57), (2.10, .57), (2.03, .33)], side * 1.27, red, rounding=.11)
    side_panel('Rear_endplate_' + str(side), [(-2.24, .93), (-2.24, 1.42), (-1.68, 1.42), (-1.59, 1.21), (-1.75, 1.02)], side * .95, red, rounding=.09)
    rod('Rear_wing_support_' + str(side), (-1.82, side * .43, .4), (-1.94, side * .43, 1.3), .035, dark)
for i in range(4):
    wing('Front_aerofoil_' + str(i), 2.21 - i * .13, .21 + i * .055, 1.27, .28, dark if i == 0 else red)
for i in range(2):
    wing('Rear_aerofoil_' + str(i), -1.99 + i * .18, 1.25 + i * .15, .94, .34, dark if i == 0 else red)
sphere('Cockpit_opening', (-.4, 0, .88), (.54, .37, .105), dark)
sphere('Cockpit_rim', (-.4, 0, .87), (.56, .395, .06), dark)
sphere('Seat', (-.68, .02, .92), (.21, .29, .2), dark)
rod('Roll_hoop', (-.89, .2, .83), (-.89, .2, 1.39), .045, dark)

# Readable livery and purposeful mechanical detail, rather than random greebles.
stroke('Nose_ivory_inlay', [(.12, 0, .811), (.75, 0, .699), (1.4, 0, .507), (2.1, 0, .353)], .018, cream)
for side in [-1, 1]:
    y = side * .903
    lettering('Sidepod_wordmark_' + str(side), 'TURBO', (-.25, y, .594), .1, cream, bounce, side)
    lettering('Rear_wing_number_' + str(side), '07', (-1.97, side * .974, 1.225), .23, cream, bounce, side)
    stroke('Floor_edge_' + str(side), [(-1.73, side * .9, .265), (-.8, side * .92, .265),
            (.55, side * .92, .265), (1.44, side * .71, .265)], .009, rim)
    stroke('Sidepod_shutline_' + str(side), [(-1.17, side * .755, .48), (-.85, side * .852, .63),
            (-.4, side * .893, .70), (.18, side * .78, .72)], .006, seam)
    for i in range(5):
        x = -.96 + i * .075
        stroke('Cooling_louvre_' + str(side) + '_' + str(i), [(x, side * .37, .96),
            (x + .05, side * .39, .89), (x + .075, side * .40, .82)], .012, seam)
    for x, z in [(-2.17, 1.39), (-1.76, 1.39), (-2.16, 1.04)]:
        cylinder('Wing_fastener_' + str(side) + str(x), (x, side * .978, z), .013, .008,
                 bronze, rotation=(math.pi / 2, 0, 0), vertices=8)
    for x in [-.66, -.15, .28]:
        cylinder('Floor_fastener_' + str(side) + str(x), (x, side * .927, .276), .009, .008,
                 rim, rotation=(math.pi / 2, 0, 0), vertices=8)
    rod('Front_pushrod_' + str(side), (.53, side * .38, .7), (1.18, side * 1.01, .46), .018, rim)
    rod('Wishbone_upper_' + str(side), (.77, side * .29, .59), (1.19, side * .95, .56), .022, dark)
    rod('Wishbone_lower_' + str(side), (.65, side * .28, .28), (1.19, side * .97, .39), .025, dark)
rod('Rear_DRS_actuator', (-2.02, 0, 1.22), (-1.86, 0, 1.49), .02, bronze)

wheels = []
for axle, x in [('Rear', -1.27), ('Front', 1.19)]:
    for side, y in [('L', -1.01), ('R', 1.01)]:
        sign = -1 if y < 0 else 1
        radius = .5 if axle == 'Rear' else .47
        depth = .53 if axle == 'Rear' else .46
        pivot = empty('Wheel_' + axle + '_' + side, (x, y, radius), root)
        wheels.append(pivot)
        # Revolved rounded tire section, with a recessed rim and exposed spokes.
        profile = [(-depth / 2, .29), (-depth / 2, radius - .08), (-depth / 2 + .045, radius - .016),
                   (-depth / 2 + .1, radius), (depth / 2 - .1, radius), (depth / 2 - .045, radius - .016),
                   (depth / 2, radius - .08), (depth / 2, .29)]
        verts = [(r * math.sin(i * math.tau / 40), y, r * math.cos(i * math.tau / 40)) for y, r in profile for i in range(40)]
        faces = []
        for j in range(len(profile)):
            for i in range(40):
                a, b = j * 40 + i, j * 40 + (i + 1) % 40
                faces.append((a, b, ((j + 1) % len(profile)) * 40 + (i + 1) % 40, ((j + 1) % len(profile)) * 40 + i))
        mesh_object('Slick_' + axle + '_' + side, verts, faces, rubber, pivot)
        cylinder('Brake_disc_' + axle + '_' + side, (0, sign * (depth / 2 - .045), 0), .25, .016, rim, pivot, (math.pi / 2, 0, 0), 32)
        cylinder('Rim_well_' + axle + '_' + side, (0, sign * (depth / 2 - .03), 0), .19, .012, dark, pivot, (math.pi / 2, 0, 0))
        for ring_radius, tube_radius, mat in [(.294, .025, rim), (.405, .009, cream)]:
            bpy.ops.mesh.primitive_torus_add(major_radius=ring_radius, minor_radius=tube_radius, major_segments=32, minor_segments=6)
            torus = finish(bpy.context.object, 'Wheel_ring_' + axle + '_' + side,
                          (0, sign * (depth / 2 + .005), 0), (1, 1, 1), mat, pivot)
            torus.rotation_euler.x = math.pi / 2
        for i in range(6):
            angle = i * math.tau / 6
            spoke = box('Spoke_' + axle + '_' + side + '_' + str(i),
                        (.17 * math.sin(angle), sign * depth / 2, .17 * math.cos(angle)),
                        (.025, .016, .12), rim, pivot, bevel=.012)
            spoke.rotation_euler.y = angle
        cylinder('Hub_' + axle + '_' + side, (0, sign * (depth / 2 + .02), 0), .075, .04, rim, pivot, (math.pi / 2, 0, 0))
        cylinder('Wheel_nut_' + axle + '_' + side, (0, sign * (depth / 2 + .05), 0), .031, .025, red, pivot, (math.pi / 2, 0, 0), vertices=6)
        for i in range(12):
            angle = math.tau * i / 12
            cylinder('Disc_drilling_' + axle + '_' + side + str(i), (.224 * math.sin(angle),
                     sign * (depth / 2 - .033), .224 * math.cos(angle)), .012, .002, seam,
                     pivot, (math.pi / 2, 0, 0), vertices=8)
        for i, char in enumerate('TURBO'):
            angle = -.52 + i * .26
            lettering('Tire_letter_' + axle + '_' + side + str(i), char,
                      (-sign * .425 * math.sin(angle), sign * (depth / 2 + .015), .425 * math.cos(angle)),
                      .064, tire_ink, pivot, sign, -sign * angle)
        lettering('Tire_compound_' + axle + '_' + side, 'S  •  07', (0, sign * (depth / 2 + .016), -.405),
                  .042, tire_ink, pivot, sign)
        valve_angle = 2.5
        sphere('Valve_' + axle + '_' + side, (.274 * math.sin(valve_angle), sign * (depth / 2 + .027),
               .274 * math.cos(valve_angle)), (.012, .015, .022), bronze, pivot, 12, 6)
        # Calipers remain attached to the axle, independently of spinning wheels.
        brake = empty('Caliper_' + axle + '_' + side, (x, y, radius), root)
        box('Caliper_body_' + axle + '_' + side, (.15, sign * (depth / 2 - .02), .05),
            (.065, .025, .115), bronze, brake, bevel=.025)
        for offset in [-.24, .24]:
            rod('Suspension_' + axle + '_' + side + str(offset),
                (x + offset, sign * .32, .5), (x, y, .48), .025, dark)

pilot = empty('Pilot', (-.4, 0, .94), bounce)
sphere('Suit', (0, 0, .04), (.25, .245, .25), fabric, pilot)
for side in [-1, 1]:
    stroke('Shoulder_harness_' + str(side), [(side * .15, -.13, .24),
           (side * .13, -.23, .14), (side * .09, -.253, -.05)], .027, cream, pilot)
    box('Harness_buckle_' + str(side), (side * .095, -.264, -.025), (.035, .009, .025), bronze, pilot, bevel=.009)
    sphere('Shoulder_pad_' + str(side), (.015, side * .23, .145), (.12, .085, .10), fabric, pilot)
    box('Suit_patch_' + str(side), (.06, side * .285, .14), (.07, .006, .032), cream, pilot, bevel=.008)
rod('Suit_zip', (.02, -.248, -.04), (.02, -.248, .18), .009, cream, pilot)
for side in [-1, 1]:
    rod('Arm_' + str(side), (.02, side * .22, .13), (.37, side * .2, -.005), .077, fabric, pilot)
    rod('Suit_piping_' + str(side), (.03, side * .278, .13), (.3, side * .252, .015), .009, cream, pilot)
    sphere('Glove_' + str(side), (.38, side * .18, -.005), (.092, .085, .085), dark, pilot)
    sphere('Glove_cuff_' + str(side), (.29, side * .205, .03), (.05, .081, .067), cream, pilot)
    for finger in range(3):
        sphere('Glove_knuckle_' + str(side) + str(finger), (.417, side * (.13 + finger * .037), .042),
               (.039, .025, .027), helmet_mat, pilot, 12, 6)
    rod('Leg_' + str(side), (.06, side * .12, -.15), (.55, side * .12, -.22), .07, dark, pilot)
    sphere('Boot_' + str(side), (.6, side * .12, -.24), (.16, .08, .07), dark, pilot)
steering = empty('SteeringWheel', (.45, 0, .05), pilot)
bpy.ops.mesh.primitive_torus_add(major_radius=.19, minor_radius=.04, major_segments=20, minor_segments=8)
obj = finish(bpy.context.object, 'Steering_rim', (0, 0, 0), (1, 1, 1), dark, steering)
obj.rotation_euler.y = math.pi / 2
head = empty('HeadLift', (0, 0, .34), pilot)
look = empty('HeadLook', parent=head)
look.rotation_euler.z = math.pi / 2

# An actual full-face racing shell: a cranial dome, swept brow and projected chin.
# Each station is (height, half-width, forward depth, rear depth).
HELMET_STATIONS = [
    (-.36, .37, .43, .37), (-.33, .47, .54, .44), (-.25, .55, .62, .50),
    (-.12, .60, .645, .55), (0, .63, .625, .58), (.14, .645, .60, .60),
    (.28, .64, .568, .60), (.43, .61, .52, .57), (.55, .55, .43, .51),
    (.66, .425, .31, .40), (.73, .255, .17, .235), (.77, .015, .012, .018),
]


def helmet_surface(z, angle, offset=0):
    z = max(HELMET_STATIONS[0][0], min(HELMET_STATIONS[-1][0], z))
    for first, after in zip(HELMET_STATIONS, HELMET_STATIONS[1:]):
        if z <= after[0]:
            t = (z - first[0]) / (after[0] - first[0])
            width, front, rear = [a + (b - a) * t for a, b in zip(first[1:], after[1:])]
            break
    cs, sn = math.cos(angle), math.sin(angle)
    depth = front if cs >= 0 else rear
    return ((width + offset) * math.copysign(abs(sn) ** .91, sn),
            -(depth + offset) * math.copysign(abs(cs) ** .88, cs), z)


def eyeport_edges(angle):
    edge = min(1, abs(angle) / 1.22) ** 1.65
    return -.04 + .145 * edge, .43 - .075 * edge


def helmet_point(lat, angle, offset=0):
    return helmet_surface(.17 + .60 * math.sin(lat), angle, offset)


def helmet_patch(name, lat_a, lat_b, angle_a, angle_b, mat, offset=.005):
    verts = [helmet_point(lat_a + (lat_b - lat_a) * j / 8,
                          angle_a + (angle_b - angle_a) * i / 3, offset)
             for j in range(9) for i in range(4)]
    faces = [(j * 4 + i, j * 4 + i + 1, j * 4 + i + 5, j * 4 + i + 4)
             for j in range(8) for i in range(3)]
    return mesh_object(name, verts, faces, mat, look)


# Full-face collectible helmet with an actual aperture and a substantial chin bar.
verts, faces = [], []
heights = [-.36, -.34, -.30, -.24, -.17, -.10, -.04, .04, .12, .22, .32,
           .43, .50, .57, .63, .68, .72, .75, .77]
count = 64
for base_z in heights:
    for i in range(count):
        angle = -math.pi + i * math.tau / count
        z = base_z
        if -.04 <= base_z <= .43:
            low, high = eyeport_edges(angle)
            t = (base_z + .04) / .47
            fade = max(0, min(1, (1.6 - abs(angle)) / .35))
            fade = fade * fade * (3 - 2 * fade)
            z += ((1 - t) * low + t * high - z) * fade
        verts.append(helmet_surface(z, angle))
for j in range(len(heights) - 1):
    for i in range(count):
        mid_angle = -math.pi + (i + .5) * math.tau / count
        if abs(mid_angle) < 1.18 and -.04 <= heights[j] < .43:
            continue
        a, b = j * count + i, j * count + (i + 1) % count
        faces.append((a, b, b + count, a + count))
helmet = mesh_object('Helmet_shell', verts, faces, helmet_mat, look)
shell = helmet.modifiers.new('Helmet shell thickness', 'SOLIDIFY')
shell.thickness = .035
bpy.context.view_layer.objects.active = helmet
bpy.ops.object.modifier_apply(modifier=shell.name)
stroke('Chin_trim', [helmet_surface(-.19, angle, .008) for angle in [-.7, -.4, 0, .4, .7]], .008, rim, look)
stroke('Helmet_base_gasket', [helmet_point(-.75, -math.pi + i * math.tau / 32, .005)
       for i in range(33)], .009, seam, look, resolution=2)
for side in [-1, 1]:
    stroke('Chin_vent_' + str(side), [helmet_surface(z, side * .43, .008)
           for z in [-.21, -.18, -.15]], .013, seam, look)
    helmet_patch('Crown_recess_' + str(side), .65, 1.2, side * .45 - .11, side * .45 + .11, seam)
    helmet_patch('Crown_vent_panel_' + str(side), .73, 1.12, side * .45 - .075, side * .45 + .075, dark, .013)
    stroke('Helmet_side_seam_' + str(side), [helmet_point(lat, side * 1.4, .007)
           for lat in [-.65, -.4, -.1, .25, .5]], .005, seam, look)
    cylinder('Helmet_badge_base_' + str(side), (side * .650, .03, .14), .147, .012,
             dark, look, (0, math.pi / 2, 0), 32)
    cylinder('Helmet_badge_' + str(side), (side * .659, .03, .14), .121, .012,
             red, look, (0, math.pi / 2, 0), 32)
    stroke('Helmet_badge_bolt_' + str(side), [(side * .670, .073, .216),
           (side * .675, -.018, .143), (side * .675, .071, .143), (side * .670, -.015, .066)], .014, cream, look)
    helmet_patch('Helmet_lower_band_' + str(side), -.62, -.43, side * 1.63 - 1.48, side * 1.63 + 1.48, red, .008)
helmet_patch('Helmet_center_stripe', .52, 1.49, -.095, .095, red, .008)
for angle in [-.11, .11]:
    stroke('Crown_pinstripe_' + str(angle), [helmet_point(lat, angle, .01)
           for lat in [.54, .8, 1.1, 1.4]], .004, cream, look)
for edge in [0, 1]:
    stroke('Eyeport_seal_' + str(edge), [helmet_surface(eyeport_edges(a)[edge], a, .008)
           for a in [-1.2 + i * 2.4 / 32 for i in range(33)]], .013, seam, look, resolution=2)
for side in [-1, 1]:
    low, high = eyeport_edges(side * 1.20)
    stroke('Eyeport_cheek_seal_' + str(side), [helmet_surface(low + (high - low) * i / 8, side * 1.20, .008)
           for i in range(9)], .013, seam, look)
for z in [-.22, -.175]:
    stroke('Chin_air_intake_' + str(z), [helmet_surface(z, a, .007) for a in [-.23, 0, .23]], .012, seam, look)

# The face sits inside the eyeport, leaving room for a flush 2 mm-style visor.
face_inset = empty('FaceInset', (0, .11, 0), look)
face = sphere('Face', (0, -.37, .15), (.515, .23, .365), skin, face_inset, 40, 24)
for vertex in face.data.vertices:
    # A rounded-square vinyl head, with a broad brow and gently flattened jaw.
    vertex.co.x = math.copysign(abs(vertex.co.x) ** .58, vertex.co.x)
    vertex.co.y = math.copysign(abs(vertex.co.y) ** .68, vertex.co.y)
    vertex.co.z = math.copysign(abs(vertex.co.z) ** .62, vertex.co.z)
face.data.update()
stroke('Smile', [(-.056, -.604, .008), (0, -.612, -.002), (.061, -.605, .012)], .006, iris_mat, face_inset)
eyes = empty('EyeExpression', (0, -.593, .19), face_inset)
blink = empty('EyeBlink', parent=eyes)
gaze = empty('EyeGaze', parent=blink)
for side in [-1, 1]:
    x = side * .235
    sphere('Eye_' + str(side), (x, -.018, -.005), (.138, .05, .159), eye_mat, gaze, 32, 20)
    sphere('Eye_glint_' + str(side), (x - .026, -.062, .044), (.013, .005, .017), white, gaze, 12, 8)
    stroke('Eyebrow_' + str(side), [(x - .12, .016, .184), (x - .03, -.002, .222 + side * .012),
           (x + .095, .015, .194)], .022, dark, eyes)
mesh_object('Nose_face', [(-.031, -.601, .027), (.031, -.601, .027), (0, -.601, .12), (0, -.657, .035)],
            [(0, 2, 3), (2, 1, 3), (1, 0, 3), (0, 1, 2)], skin, face_inset)
# Thin curved visor patch around the front of the helmet, rotating at temple height.
visor = empty('VisorPivot', (0, .015, .31), look)


def visor_point(t, angle):
    low, high = eyeport_edges(angle)
    x, y, z = helmet_surface(low + t * (high - low), angle, .018)
    return x, y - .015, z - .31


verts, faces = [], []
for j in range(11):
    t = j / 10
    for i in range(33):
        angle = -1.40 + i * 2.80 / 32
        verts.append(visor_point(t, angle))
for j in range(10):
    for i in range(32):
        a = j * 33 + i
        faces.append((a, a + 1, a + 34, a + 33))
mesh = bpy.data.meshes.new('Curved visor mesh')
mesh.from_pydata(verts, [], faces)
mesh.update()
obj = bpy.data.objects.new('Visor', mesh)
scene.collection.objects.link(obj)
obj.parent = visor
obj.data.materials.append(visor_mat)
for poly in mesh.polygons:
    poly.use_smooth = True
solid = obj.modifiers.new('Visor thickness', 'SOLIDIFY')
solid.thickness = .012
bpy.context.view_layer.objects.active = obj
obj.select_set(True)
bpy.ops.object.modifier_apply(modifier=solid.name)
for side in [-1, 1]:
    sphere('Visor_hinge_' + str(side), (side * .636, .015, .31), (.035, .052, .052), rim, look, 16, 8)
    cylinder('Hinge_recess_' + str(side), (side * .67, .015, .31), .028, .01,
             seam, look, (0, math.pi / 2, 0), 16)
    cylinder('Hinge_screw_' + str(side), (side * .681, .015, .31), .014, .008,
             bronze, look, (0, math.pi / 2, 0), 8)
    anchor = visor_point(.60, side * 1.4)
    stroke('Visor_hinge_arm_' + str(side), [(side * .638, 0, 0),
           (side * .646, -.055, -.025), anchor], .016, dark, visor)
for t, mat in [(0, seam), (1, glass_edge)]:
    stroke('Visor_edge_' + str(t), [visor_point(t, a)
           for a in [-1.40 + i * 2.80 / 32 for i in range(33)]], .007, mat, visor, resolution=2)

# Pop! Rides-inspired proportions: shorter body, deeper sidepods, big round tires.
# Counter-scale the pilot so the character retains its rounded-square head.
tilt.scale = (.87, 1.04, 1.12)
pilot.scale = (1 / .87, 1 / 1.04, 1 / 1.12)
for obj in root.children:
    if obj.name.startswith(('Wheel_', 'Caliper_')):
        obj.location.x *= .87
        obj.location.y *= 1.04
        obj.location.z *= 1.14
        obj.scale = (1.14, 1.10, 1.14)


def clip(name, tracks, frames=(1, 16, 31, 46, 61), linear=False):
    """One named NLA track per object; the exporter merges matching names."""
    for obj, prop, values in tracks:
        obj.animation_data_create()
        obj.animation_data.action = None
        original = getattr(obj, prop).copy()
        for frame, value in zip(frames, values):
            setattr(obj, prop, value)
            obj.keyframe_insert(data_path=prop, frame=frame, group=name)
        action = obj.animation_data.action
        action.name = name + '__' + obj.name
        if linear:
            for layer in action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for curve in bag.fcurves:
                            for key in curve.keyframe_points:
                                key.interpolation = 'LINEAR'
        slot = obj.animation_data.action_slot
        track = obj.animation_data.nla_tracks.new()
        track.name = name
        nla = track.strips.new(name, 1, action)
        nla.action_slot = slot
        nla.extrapolation = 'NOTHING'
        track.mute = True
        obj.animation_data.action = None
        setattr(obj, prop, original)


clip('idle', [(bounce, 'location', [(0, 0, z) for z in [0, .012, 0, -.007, 0]])])
clip('engine_vibration', [(bounce, 'location', [(0, 0, z) for z in [0, .019, -.012, .016, 0]])])
clip('start', [(tilt, 'rotation_euler', [(0, y, 0) for y in [0, .035, -.02, .012, 0]])])
for level in range(1, 5):
    clip('speed_' + str(level), [(wheel, 'rotation_euler', [(0, -math.tau * level * t / 4, 0) for t in range(5)]) for wheel in wheels], linear=True)
head_rest = tuple(head.location)
head_up = (0, 0, head_rest[2] + .36)
clip('head_up', [(head, 'location', [head_rest, head_up])], frames=(1, 22))
clip('head_down', [(head, 'location', [head_up, head_rest])], frames=(1, 22))
VISOR_OPEN_ANGLE = -1.38
REVEAL_SQUINT = .8
clip('visor_open', [(visor, 'rotation_euler', [(0, 0, 0), (VISOR_OPEN_ANGLE, 0, 0)])], frames=(1, 19))
clip('visor_close', [(visor, 'rotation_euler', [(VISOR_OPEN_ANGLE, 0, 0), (0, 0, 0)])], frames=(1, 19))
clip('subtle_look', [(look, 'rotation_euler', [(0, 0, math.pi / 2), (.18, -.08, .12)]),
                     (eyes, 'scale', [(1, 1, 1), (1, 1, REVEAL_SQUINT)])], frames=(1, 25))
clip('body_tilt', [(tilt, 'rotation_euler', [(0, 0, 0), (0, .065, -.018)])], frames=(1, 31))
clip('victory_boost', [(bounce, 'scale', [(1, 1, 1), (1.025, 1, .98), (1, 1, 1), (1.015, 1, .99), (1, 1, 1)])])


def bake_contact_occlusion():
    """Bake soft local contact shading to vertex colors; no image textures or runtime AO."""
    bpy.context.view_layer.update()
    meshes = [obj for obj in root.children_recursive if obj.type == 'MESH']
    verts, faces = [], []
    delicate = ('Visor', 'Eye', 'Iris', 'Pupil', 'Face', 'Cheek', 'Nose_face', 'Smile')
    for obj in meshes:
        if obj.name.startswith(delicate):
            continue
        start = len(verts)
        verts.extend(obj.matrix_world @ vertex.co for vertex in obj.data.vertices)
        faces.extend(tuple(start + index for index in polygon.vertices) for polygon in obj.data.polygons)
    bvh = BVHTree.FromPolygons(verts, faces)
    for obj in meshes:
        colors = obj.data.color_attributes.new(name='ContactAO', type='BYTE_COLOR', domain='POINT')
        normals = obj.matrix_world.inverted_safe().transposed().to_3x3()
        for vertex, color in zip(obj.data.vertices, colors.data):
            ao = 1
            if not obj.name.startswith(delicate):
                normal = (normals @ vertex.normal).normalized()
                origin = obj.matrix_world @ vertex.co + normal * .006
                axis = Vector((0, 0, 1)) if abs(normal.z) < .9 else Vector((1, 0, 0))
                tangent = normal.cross(axis).normalized()
                bitangent = normal.cross(tangent)
                blocked = 0
                for direction in [normal, (normal * .65 + tangent * .76), (normal * .65 - tangent * .76),
                                  (normal * .65 + bitangent * .76), (normal * .65 - bitangent * .76)]:
                    hit, _, _, distance = bvh.ray_cast(origin, direction.normalized(), .28)
                    if hit is not None:
                        blocked += (1 - distance / .28) / 5
                ao = 1 - .36 * blocked
            blush = 0
            if obj.name == 'Face':
                blush = math.exp(-((abs(vertex.co.x) - .6) / .24) ** 2 - ((vertex.co.z + .4) / .3) ** 2) * max(0, -vertex.co.y)
            color.color = (ao, ao * (1 - .07 * blush), ao * (1 - .03 * blush), 1)
    for mat in bpy.data.materials:
        if not mat.use_nodes:
            continue
        shader = mat.node_tree.nodes.get('Principled BSDF')
        if not shader:
            continue
        base = tuple(shader.inputs['Base Color'].default_value)
        attribute = mat.node_tree.nodes.new('ShaderNodeVertexColor')
        attribute.layer_name = 'ContactAO'
        multiply = mat.node_tree.nodes.new('ShaderNodeMix')
        multiply.data_type = 'RGBA'
        multiply.blend_type = 'MULTIPLY'
        multiply.inputs[0].default_value = 1
        multiply.inputs[6].default_value = base
        mat.node_tree.links.new(attribute.outputs['Color'], multiply.inputs[7])
        mat.node_tree.links.new(multiply.outputs[2], shader.inputs['Base Color'])
    print('CONTACT_AO_BAKED', len(meshes), 'objects', len(verts), 'vertices', flush=True)


bake_contact_occlusion()
for datablock in list(bpy.data.fonts):
    if datablock.users == 0 and datablock.name != 'Bfont':
        bpy.data.fonts.remove(datablock)
scene.frame_set(1)
rest_transforms = {}
for obj in root.children_recursive:
    if obj.animation_data:
        x, y, z = obj.location
        q = obj.rotation_euler.to_quaternion()
        sx, sy, sz = obj.scale
        rest_transforms[obj.name] = {'translation': [x, z, -y],
                                     'rotation': [q.x, q.z, -q.y, q.w], 'scale': [sx, sz, sy]}
root['description'] = 'TurboTears password racer. Independent speed and reveal layers; no password data.'
root['art_direction'] = 'Rounded-square vinyl pilot, black domed eyes, compact cartoon F1 car with oversized wheels.'
# Ready-to-open Blender source, with a useful camera and studio lighting.
bpy.ops.object.camera_add(location=(.08, -9, 1.37))
camera = bpy.context.object
camera.name = 'Preview_camera'
camera.rotation_euler = (Vector((.08, 0, 1.37)) - camera.location).to_track_quat('-Z', 'Y').to_euler()
camera.data.type, camera.data.ortho_scale = 'ORTHO', 6.24
scene.camera = camera
for name, loc, energy, size in [('Key', (1, -4, 6), 750, 5), ('Rim', (-3, 2, 4), 650, 3),
                               ('Face_softbox', (1, -5, 2.5), 200, 4)]:
    bpy.ops.object.light_add(type='AREA', location=loc)
    lamp = bpy.context.object
    lamp.name = name
    lamp.data.energy, lamp.data.shape, lamp.data.size = energy, 'DISK', size
    lamp.rotation_euler = (Vector((0, 0, .8)) - lamp.location).to_track_quat('-Z', 'Y').to_euler()
scene.world.color = (.18, .18, .18)
scene.render.resolution_x, scene.render.resolution_y = 1440, 675
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'WEBP'
scene.render.image_settings.quality = 90
scene.render.film_transparent = True
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type == 'VIEW_3D':
            area.spaces.active.region_3d.view_perspective = 'CAMERA'
            area.spaces.active.shading.type = 'MATERIAL'
scene.render.engine = 'CYCLES'
scene.cycles.samples = 48
scene.cycles.use_denoising = True
bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / 'password-racer.blend'))
scene.render.filepath = str(OUTPUT / 'poster.webp')
bpy.ops.render.render(write_still=True)
# A large, inspectable still of the same reveal pose, using the same side camera.
head.location = head_up
visor.rotation_euler = (VISOR_OPEN_ANGLE, 0, 0)
look.rotation_euler = (.18, -.08, .12)
eyes.scale = (1, 1, REVEAL_SQUINT)
bpy.context.view_layer.update()
scene.render.filepath = str(SOURCE / 'detail-reveal.webp')
bpy.ops.render.render(write_still=True)
head.location = head_rest
visor.rotation_euler = (0, 0, 0)
look.rotation_euler = (0, 0, math.pi / 2)
eyes.scale = (1, 1, 1)
bpy.context.view_layer.update()
# Muted authored tracks stay editable in .blend, but must be enabled for NLA export.
for obj in bpy.data.objects:
    if obj.animation_data:
        for track in obj.animation_data.nla_tracks:
            track.mute = False
bpy.ops.object.select_all(action='DESELECT')
root.select_set(True)
for obj in root.children_recursive:
    obj.select_set(True)
bpy.ops.export_scene.gltf(
    filepath=str(OUTPUT / 'password-racer.glb'), export_format='GLB',
    export_animations=True, export_animation_mode='NLA_TRACKS',
    export_frame_range=False, export_force_sampling=True,
    export_optimize_animation_size=True, export_materials='EXPORT',
    export_cameras=False, export_lights=False, export_extras=True, use_selection=True,
)
# NLA tracks include both opening and closing actions. Their combined evaluation
# can change the exported default pose; keep the authored rest pose for GLB viewers.
path = OUTPUT / 'password-racer.glb'
raw = path.read_bytes()
json_length = struct.unpack_from('<I', raw, 12)[0]
document = json.loads(raw[20:20 + json_length])
for node in document['nodes']:
    if node.get('name') in rest_transforms:
        node.update(rest_transforms[node['name']])
encoded = json.dumps(document, separators=(',', ':')).encode()
encoded += b' ' * (-len(encoded) % 4)
binary_chunk = raw[20 + json_length:]
normalized_path = path.with_suffix('.next.glb')
normalized_path.write_bytes(struct.pack('<4sII', b'glTF', 2, 20 + len(encoded) + len(binary_chunk))
                            + struct.pack('<I4s', len(encoded), b'JSON') + encoded + binary_chunk)
normalized_path.replace(path)
print('PASSWORD_RACER_EXPORTED', OUTPUT / 'password-racer.glb')
