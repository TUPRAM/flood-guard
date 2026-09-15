"""Build and render the editable FloodGuard illustrative neighborhood.

Run with Blender's --background --python, then -- --help. All dimensions are
metres in an invented neighborhood; water levels are editorial states, not
hydrological data. A deterministic seed keeps geography identical in every shot.
"""

import argparse
import json
import math
from pathlib import Path
import random
import sys

import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from architecture import build_house, build_clinic, _Meshes, _material
from vegetation import build_tree, build_banana, build_shrub

REPO = HERE.parents[1]
OUT = REPO / "outputs/landing-v2-assets"
SOURCE = REPO / "assets/floodguard-neighborhood"
PUBLIC = REPO / "apps/web/public/landing/floodguard-v2"
WIDTH, HEIGHT = 1536, 1152
WATER_LEVELS = {"W0": -.38, "W1": .18, "W2": .63}
RNG = random.Random(41127)


def empty(name):
    obj = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(obj)
    return obj


def river_y(x):
    return -19 + 3.1 * math.sin(x / 22) + .7 * math.sin(x / 9)


def road_y(x):
    return 1.8 * math.sin(x / 23) + .55 * math.sin(x / 10)


def elevation(x, y):
    river = math.exp(-((y - river_y(x)) / 4.7) ** 2)
    lowland = math.exp(-(x / 15.8) ** 2 - ((y + 4.7) / 16) ** 2)
    variation = .045 * math.sin(x / 2.2) * math.sin(y / 3.9) + .08 * math.sin(x / 11 + y / 16)
    return .94 + variation - 1.8 * river - .96 * lowland


def mesh_object(name, verts, faces, material, parent=None):
    mesh = bpy.data.meshes.new(name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def terrain_material():
    mat = _material("MeadowLoam", (.43, .46, .24), texture=.08)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    geom = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = .38
    noise.inputs["Detail"].default_value = 4.5
    links.new(geom.outputs["Object"], noise.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (.075, .13, .029, 1)
    ramp.color_ramp.elements[0].position = .22
    ramp.color_ramp.elements[1].color = (.35, .33, .17, 1)
    ramp.color_ramp.elements[1].position = .78
    ramp.color_ramp.elements.new(.47).color = (.19, .25, .082, 1)
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    return mat


def build_ground():
    parent = empty("01_Terrain_and_river_banks")
    n, m, step = 290, 236, .5
    verts = []
    for y in range(m + 1):
        for x in range(n + 1):
            px, py = x * step - 72.5, y * step - 54
            px += (math.sin(py / 6) * 1.8 + math.sin(py / 2.1) * .5) * (abs(px) / 72.5) ** 8
            py += (math.sin(px / 8) * 1.3 + math.sin(px / 2.9) * .7) * (abs(py - 5) / 59) ** 8
            verts.append((px, py, elevation(px, py)))
    faces = [(i, i + 1, i + n + 2, i + n + 1) for y in range(m) for x in range(n) for i in [y * (n + 1) + x]]
    mesh_object("Sculpted_floodplain", verts, faces, terrain_material(), parent)
    # A broad matte backdrop avoids a sky/horizon break during the aerial move.
    mat = _material("EditorialPaper", (.79, .76, .65), texture=.025)
    mesh_object("Paper_backdrop", [(-800, -800, -1.4), (800, -800, -1.4), (800, 800, -1.4), (-800, 800, -1.4)], [(0, 1, 2, 3)], mat, parent)
    return parent


def road_strip(name, points, width, material, parent, offset=.065):
    verts = []
    for i, (x, y) in enumerate(points):
        before, after = Vector(points[max(0, i - 1)]), Vector(points[min(len(points) - 1, i + 1)])
        direction = (after - before).normalized()
        normal = Vector((-direction.y, direction.x))
        for side in (-1, 1):
            px, py = Vector((x, y)) + normal * width * .5 * side
            verts.append((px, py, elevation(px, py) + offset))
    faces = [(i * 2, i * 2 + 1, i * 2 + 3, i * 2 + 2) for i in range(len(points) - 1)]
    return mesh_object(name, verts, faces, material, parent)


def build_roads():
    root = empty("02_Roads_curbs_and_access")
    asphalt = _material("WeatheredAsphalt", (.40, .40, .36), texture=.022)
    concrete = _material("ConcreteRoadEdge", (.69, .67, .56), texture=.024)
    main = [(x / 2, road_y(x / 2)) for x in range(-140, 141)]
    road_strip("Main_connecting_road_edges", main, 7.9, concrete, root, .045)
    road_strip("Main_connecting_road_surface", main, 6.9, asphalt, root, .072)
    for x in (-41, -8, 24, 56):
        points = [(x + 1.1 * math.sin(y / 11), y) for y in range(1, 61)]
        road_strip(f"Lane_{x}_edges", points, 4.8, concrete, root, .05)
        road_strip(f"Lane_{x}_asphalt", points, 4, asphalt, root, .075)
    rear = [(x, 32 + .8 * math.sin(x / 18)) for x in range(-69, 70)]
    road_strip("Rear_lane_edges", rear, 4.4, concrete, root)
    road_strip("Rear_lane_surface", rear, 3.8, asphalt, root, .08)
    paint = _material("WornRoadPaint", (.80, .77, .61), texture=.006)
    for x in range(-66, 68, 5):
        points = [(x + t / 4, road_y(x + t / 4)) for t in range(7)]
        road_strip(f"Center_dash_{x}", points, .095, paint, root, .087)
    return root


def garden(name, x, y, z, width=14, depth=14, clinic=False):
    root = empty(name + "_Garden_boundary")
    palette = {"wall": _material("GardenLimewash", (.71, .69, .57), texture=.03),
               "cap": _material("GardenWallCaps", (.80, .76, .62), texture=.025),
               "iron": _material("GardenIron", (.18, .22, .18), roughness=.49, metallic=.5),
               "earth": _material("GardenGravel", (.57, .54, .41), texture=.045),
               "pot": _material("Earthenware", (.40, .21, .115), texture=.035)}
    parts = _Meshes(root, palette)
    front, back = y - depth / 2, y + depth / 2
    # Grass beds flank a narrow stone walk; the entire yard is not a concrete slab.
    parts.box("earth", (x, y - depth / 4, z - .01), (3.1, depth / 2 - .3, .11))
    # Two front wall sections leave a physical gate and driveway.
    gate = 3.6 if clinic else 2.8
    section = (width - gate) / 2
    for side in (-1, 1):
        cx = x + side * (gate / 2 + section / 2)
        parts.box("wall", (cx, front, z + .40), (section, .25, .80))
        parts.box("cap", (cx, front, z + .84), (section + .08, .34, .09))
        parts.box("wall", (x + side * width / 2, y, z + .36), (.23, depth, .72))
        parts.box("cap", (x + side * width / 2, y, z + .77), (.31, depth, .10))
        for px in (x + side * gate / 2, x + side * width / 2):
            parts.box("wall", (px, front, z + .82), (.44, .44, 1.64))
            parts.box("cap", (px, front, z + 1.69), (.55, .55, .13))
    parts.box("wall", (x, back, z + .34), (width, .23, .68))
    # Slender railings are editable geometry, not a texture decal.
    for side in (-1, 1):
        for i in range(int(section / .21)):
            px = x + side * (gate / 2 + .18 + i * .21)
            parts.box("iron", (px, front, z + 1.11), (.025, .028, .53))
        parts.box("iron", (x + side * (gate / 2 + section / 2), front, z + 1.36), (section, .035, .045))
    for i in range(14):
        px = x - gate / 2 + .1 + i * (gate - .2) / 13
        parts.box("iron", (px, front, z + .77), (.045, .06, 1.40))
    for level in (.16, 1.4):
        parts.box("iron", (x, front, z + level), (gate, .065, .08))
    for side in (-1, 1):
        parts.cylinder("pot", (x + side * 3.7, y - 3.7, z), (x + side * 3.7, y - 3.7, z + .56), .37, 16)
        for i in range(10):
            parts.box("cap", (x + side * (width / 2 - 1), front + .8 + i * .49, z + .07), (.8, .41, .10))
        parts.box("earth", (x + side * (width / 2 - 1.6), y + 1, z), (1.3, 5, .1))
        parts.box("cap", (x + side * (width / 2 - 2.3), y + 1, z + .12), (.14, 5.2, .24))
    parts.finish()
    return root


def build_architecture():
    root = empty("03_Architecture_and_parcels")
    plots = [(-24, 12, 1.14, 0, True), (-7, 15, .87, 1, False), (8, 12, .91, 2, False),
             (42, 12, .96, 3, False), (-56, 12, .92, 1, False), (-41, 13, .81, 2, False)]
    for row, y in enumerate((28, 46)):
        for col, x in enumerate((-58, -43, -25, -9, 8, 26, 43, 59)):
            plots.append((x + RNG.uniform(-1.7, 1.7), y + RNG.uniform(-2.1, 2.1), RNG.uniform(.65, .93), (row * 3 + col) % 4, False))
    for i, (x, y, scale, variant, hero) in enumerate(plots):
        z = max(.80, elevation(x, y))
        house = build_house("Home_story" if hero else f"Residence_{i:02}", (x, y, z), rotation=0 if hero else RNG.uniform(-.07, .07), scale=scale, variant=variant, hero=hero)
        house.parent = root
        garden(f"Parcel_{i:02}", x, y, z, 14, 14).parent = root
        for side in (-1, 1):
            for j in range(3):
                build_shrub(f"Parcel_{i:02}_border_{side}_{j}", (x + side * 5.8, y - 4.2 + j * 1.25, z), .95, seed=1000 + i * 7 + j).parent = root
        tree = build_tree(f"Parcel_{i:02}_shade", (x - 5.6, y + 3.6, z), .9 + (i % 3) * .12, seed=1200 + i, quality="background")
        tree.scale.x *= 1.3
        tree.scale.y *= 1.3
        tree.parent = root
        build_banana(f"Parcel_{i:02}_banana", (x + 5, y + 2.5, z), 1.08, seed=1300 + i).parent = root
        entrance = [(x, y - 7), (x, y - 8), (x, road_y(x) + 3.45)] if y < 20 else [(x, y - 7), (x, y - 8.5)]
        road_strip(f"Driveway_{i:02}", entrance, 2.6, _material("Driveway", (.62, .59, .49), texture=.025), root, .11)
    x, y, z = 27, 12, 1.03
    build_clinic("Clinic_story", (x, y, z), scale=1).parent = root
    garden("Clinic", x, y, z, 18, 16, True).parent = root
    road_strip("Clinic_driveway", [(27, 4), (27, road_y(27) + 3)], 4, _material("Driveway", (.62, .59, .49), texture=.025), root, .13)
    # A few distant homes across the river establish a larger lived-in place.
    for i, x in enumerate((-50, -33, 35, 53)):
        y = -37 + RNG.uniform(-1.5, 1.5)
        z = elevation(x, y)
        build_house(f"Riverbank_home_{i}", (x, y, z), scale=.73, variant=i).parent = root
        garden(f"Riverbank_{i}", x, y, z, 12, 11).parent = root
    return root


def build_landscape():
    root = empty("04_Trees_banana_gardens_and_meadow")
    trees = [(-33, 13, 1.04), (-15, 15, .84), (17, 17, 1.02), (37, 19, 1), (-63, 16, .92), (-47, 23, 1),
             (-31, 31, 1.03), (-16, 31, .86), (0, 28, .93), (17, 31, 1.1), (34, 34, .99), (49, 30, 1.13),
             (-61, 43, 1.02), (-34, 47, 1.1), (-17, 51, 1.1), (0, 47, 1), (18, 48, .98), (36, 48, 1.15), (52, 49, 1.1),
             (-66, -9, .81), (-45, -9, .78), (-34, -8, .82), (36, -8, .86), (49, -7, .81), (62, -6, .97),
             (-60, -36, .9), (-43, -34, .88), (44, -35, .82), (62, -36, .92), (-8, 60, 1.1), (23, 61, 1.06)]
    for i, (x, y, scale) in enumerate(trees):
        tree = build_tree(f"Canopy_{i:02}", (x, y, elevation(x, y)), scale * 1.08, seed=i + 21, quality="hero" if i < 6 else "background")
        tree.scale.x *= 1.25
        tree.scale.y *= 1.25
        tree.parent = root
    for i, (x, y) in enumerate([(-30, 7), (-18, 19), (2, 7), (34, 6), (50, 17), (-55, 22), (-37, 30), (3, 38), (45, 45), (-53, -29), (31, -31), (59, -30)]):
        build_banana(f"Banana_clump_{i:02}", (x, y, elevation(x, y)), .8 + RNG.random() * .35, seed=i + 120).parent = root
    for i in range(230):
        x = RNG.uniform(-67, 68)
        y = RNG.choice((RNG.uniform(-12, -6), RNG.uniform(6, 9), RNG.uniform(20, 26), RNG.uniform(53, 62)))
        if -7 < x < 15 and y < 6:
            continue
        build_shrub(f"Garden_shrub_{i:03}", (x, y, elevation(x, y)), RNG.uniform(.65, 1.35), seed=260 + i).parent = root
    for i in range(140):
        x = RNG.uniform(-70, 70)
        side = -1 if i % 2 else 1
        y = river_y(x) + side * RNG.uniform(5, 8)
        build_shrub(f"Riverbank_scrub_{i:03}", (x, y, elevation(x, y)), RNG.uniform(.45, 1.2), seed=1600 + i).parent = root
    for i in range(16):
        x = -67 + i * 8.6
        y = 59 + RNG.uniform(-2, 3)
        tree = build_tree(f"Rear_grove_{i:02}", (x, y, elevation(x, y)), RNG.uniform(1, 1.35), seed=1800 + i, quality="background")
        tree.scale.x *= 1.3
        tree.scale.y *= 1.3
        tree.parent = root
    # Curved grass blades/reeds form meadow texture at grazing camera angles.
    mats = [_material(f"MeadowBlade{i}", color) for i, color in enumerate(((.27, .33, .13), (.42, .44, .19), (.55, .51, .28), (.31, .39, .17)))]
    verts, faces, indices = [], [], []
    for i in range(70000):
        x, y = RNG.uniform(-71, 71), RNG.uniform(-49, 62)
        d = abs(y - river_y(x))
        if d < 2.6 or (y > -5 and y < 52) or (y < -29 and abs(x) > 25):
            continue
        z = elevation(x, y)
        for blade in range(3):
            angle = RNG.random() * math.tau
            length = RNG.uniform(.18, .64) * (1.5 if d < 7 else 1)
            width = RNG.uniform(.025, .06)
            dx, dy = math.cos(angle), math.sin(angle)
            at = len(verts)
            verts.extend(((x - dy * width, y + dx * width, z), (x + dy * width, y - dx * width, z),
                          (x + dx * length * .22, y + dy * length * .22, z + length * .65),
                          (x + dx * length * .45, y + dy * length * .45, z + length)))
            faces.extend(((at, at + 1, at + 2), (at + 1, at + 3, at + 2)))
            indices.extend((i % 4, i % 4))
    obj = mesh_object("Meadow_individual_blades", verts, faces, mats[0], root)
    for mat in mats[1:]:
        obj.data.materials.append(mat)
    for face, index in zip(obj.data.polygons, indices):
        face.material_index = index
    return root


def build_water():
    root = empty("05_Water_illustrative_level_control")
    root["W0_dry_channel"] = WATER_LEVELS["W0"]
    root["W1_rising"] = WATER_LEVELS["W1"]
    root["W2_connection_affected"] = WATER_LEVELS["W2"]
    mat = _material("RiverWater", (.095, .18, .155), roughness=.29)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["IOR"].default_value = 1.333
    shader.inputs["Transmission Weight"].default_value = .13
    shader.inputs["Metallic"].default_value = .12
    coords = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeVectorMath")
    mapping.operation = "MULTIPLY"
    mapping.inputs[1].default_value = (.8, 3.8, 1)
    links.new(coords.outputs["Object"], mapping.inputs[0])
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.3
    noise.inputs["Detail"].default_value = 3
    links.new(mapping.outputs[0], noise.inputs["Vector"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .18
    bump.inputs["Distance"].default_value = .065
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    obj = mesh_object("Controllable_water_surface", [(-73, -49, 0), (73, -49, 0), (73, 27, 0), (-73, 27, 0)], [(0, 1, 2, 3)], mat, root)
    obj.location.z = WATER_LEVELS["W0"]
    return obj


def lighting():
    world = bpy.data.worlds.new("Warm_overcast_sky")
    bpy.context.scene.world = world
    world.use_nodes = True
    world.node_tree.nodes["Background"].inputs["Color"].default_value = (.71, .78, .83, 1)
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = .4
    data = bpy.data.lights.new("Large_soft_morning_key", "AREA")
    light = bpy.data.objects.new(data.name, data)
    bpy.context.collection.objects.link(light)
    light.location = (-38, -28, 72)
    light.rotation_euler = (Vector((0, 10, 0)) - light.location).to_track_quat("-Z", "Y").to_euler()
    data.energy, data.shape, data.size = 34000, "DISK", 25
    data.color = (1, .91, .75)
    sun_data = bpy.data.lights.new("Soft_sun", "SUN")
    sun = bpy.data.objects.new(sun_data.name, sun_data)
    bpy.context.collection.objects.link(sun)
    sun.rotation_euler = (.42, -.46, -.45)
    sun_data.energy, sun_data.angle = 1.45, .14


def finish_scene():
    """Soft editorial edges and editable camera/water keyframes in the master."""
    scene = bpy.context.scene
    bpy.data.objects["Paper_backdrop"].hide_render = True
    scene.world.node_tree.nodes["Background"].inputs["Color"].default_value = (.83, .81, .73, 1)
    scene.world.node_tree.nodes["Background"].inputs["Strength"].default_value = .52
    for name in ("FG_MeadowLoam", "FG_RiverWater"):
        material = bpy.data.materials[name]
        nodes, links = material.node_tree.nodes, material.node_tree.links
        if nodes.get("EditorialEdgeFade"):
            continue
        coordinates = nodes.new("ShaderNodeNewGeometry")
        separate = nodes.new("ShaderNodeSeparateXYZ")
        links.new(coordinates.outputs["Position"], separate.inputs[0])
        axes = []
        for axis, extent in (("X", 73), ("Y", 64)):
            absolute = nodes.new("ShaderNodeMath")
            absolute.operation = "ABSOLUTE"
            links.new(separate.outputs[axis], absolute.inputs[0])
            divide = nodes.new("ShaderNodeMath")
            divide.operation = "DIVIDE"
            divide.inputs[1].default_value = extent
            links.new(absolute.outputs[0], divide.inputs[0])
            axes.append(divide)
        maximum = nodes.new("ShaderNodeMath")
        maximum.operation = "MAXIMUM"
        for index, axis in enumerate(axes):
            links.new(axis.outputs[0], maximum.inputs[index])
        mapping = nodes.new("ShaderNodeMapRange")
        mapping.interpolation_type = "SMOOTHSTEP"
        mapping.inputs["From Min"].default_value = .86
        mapping.inputs["From Max"].default_value = 1
        links.new(maximum.outputs[0], mapping.inputs["Value"])
        transparent = nodes.new("ShaderNodeBsdfTransparent")
        mix = nodes.new("ShaderNodeMixShader")
        mix.name = "EditorialEdgeFade"
        links.new(mapping.outputs[0], mix.inputs[0])
        links.new(nodes.get("Principled BSDF").outputs[0], mix.inputs[1])
        links.new(transparent.outputs[0], mix.inputs[2])
        links.new(mix.outputs[0], nodes.get("Material Output").inputs["Surface"])
    water = bpy.data.objects["Controllable_water_surface"]
    # Render jobs explicitly choose their camera and water. Keyframes make the
    # same controlled sequence available when the source is opened interactively.
    if not scene.camera.animation_data:
        for frame, progress in ((1, 0), (48, 1), (144, 1)):
            camera_at(progress)
            scene.camera.keyframe_insert(data_path="location", frame=frame)
            scene.camera.keyframe_insert(data_path="rotation_euler", frame=frame)
        for frame, state in ((1, "W0"), (48, "W0"), (96, "W1"), (144, "W2")):
            water.location.z = WATER_LEVELS[state]
            water.keyframe_insert(data_path="location", frame=frame)
        scene.frame_end = 144
        scene.timeline_markers.new("Wide drone overview", frame=1)
        scene.timeline_markers.new("Neighborhood settled / W0", frame=48)
        scene.timeline_markers.new("Rising water / W1", frame=96)
        scene.timeline_markers.new("Affected connection / W2", frame=144)
    scene.frame_set(48)


def camera_at(t):
    scene = bpy.context.scene
    camera = scene.camera
    start, end = Vector((105, -136, 154)), Vector((69, -95, 92))
    target = Vector((0, 9, 2))
    camera.location = start.lerp(end, t)
    camera.rotation_euler = (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    camera.data.type = "PERSP"
    camera.data.lens = 48
    camera.data.clip_end = 1500
    scene.view_layers.update()


def render_settings(samples=32, width=1536):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 6
    scene.cycles.transparent_max_bounces = 4
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        scene.cycles.device = "GPU"
    except (TypeError, RuntimeError):
        scene.cycles.device = "CPU"
    scene.render.resolution_x = width
    scene.render.resolution_y = round(width * HEIGHT / WIDTH)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = True
    scene.render.threads_mode = "AUTO"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = .2
    scene.render.use_file_extension = True
    scene.render.use_persistent_data = True


def anchors():
    camera_at(1)
    def point(x, y, z=None):
        z = elevation(x, y) + .12 if z is None else z
        p = world_to_camera_view(bpy.context.scene, bpy.context.scene.camera, Vector((x, y, z)))
        return [round(p.x * WIDTH, 2), round((1 - p.y) * HEIGHT, 2)]
    route_world = [(-24, 5, 1.12), (-24, road_y(-24), None)]
    route_world += [(x, road_y(x), None) for x in range(-20, 29, 4)]
    route_world += [(27, 4, 1.1)]
    route = [point(x, y, z) for x, y, z in route_world]
    landmarks = {"home": point(-24, 5, 1.12), "clinic": point(27, 4, 1.1), "route": route,
                 "affected": [3, 10], "report": point(3, -2.2),
                 "selection": [point(-12, -6), point(15, -6), point(15, 6), point(-12, 6)]}
    parent = empty("06_Story_attachment_points") if not bpy.data.objects.get("06_Story_attachment_points") else bpy.data.objects["06_Story_attachment_points"]
    for name, position in (("Home_gate", (-24, 5, 1.12)), ("Clinic_gate", (27, 4, 1.1)), ("Observation", (3, -2.2, .3))):
        obj = bpy.data.objects.get("Anchor_" + name) or empty("Anchor_" + name)
        obj.location = position
        obj.parent = parent
        obj.empty_display_type, obj.empty_display_size = "SPHERE", .6
    return landmarks


def write_manifest(frame_count: int = 16) -> dict:
    """Record image-space registration without changing the saved camera or animation."""
    if frame_count < 2:
        raise ValueError("The camera approach requires at least two frames")
    PUBLIC.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    source_camera = scene.camera
    projection_camera = source_camera.copy()
    projection_data = source_camera.data.copy()
    projection_camera.data = projection_data
    projection_camera.animation_data_clear()
    projection_data.animation_data_clear()
    scene.collection.objects.link(projection_camera)
    scene.camera = projection_camera
    # These three points span the main frontage and the rear neighborhood, all
    # on one plane. Perspective and elevated roofs still have residual parallax.
    world_triangle = [(-35, 2, 1), (35, 2, 1), (0, 40, 1)]
    diagnostics = [
        {"name": "rear-west-ground", "kind": "ground", "world": [-35, 40, 1]},
        {"name": "rear-east-ground", "kind": "ground", "world": [35, 40, 1]},
        {"name": "center-ground", "kind": "ground", "world": [0, 21, 1]},
    ]
    for name in ("Home_story", "Residence_02", "Clinic_story"):
        building = bpy.data.objects.get(name)
        if building is None:
            continue
        roof_parts = [obj for obj in building.children if obj.type == "MESH"
                      and any("RoofTile" in mat.name for mat in obj.data.materials)]
        if not roof_parts:
            continue
        roof_height = max((obj.matrix_world @ Vector(corner)).z
                          for obj in roof_parts for corner in obj.bound_box)
        center = building.matrix_world.translation
        diagnostics.append({"name": name + "-roof-center", "kind": "roof",
                            "world": [round(center.x, 6), round(center.y, 6), round(roof_height, 6)]})

    def projected(world):
        point = world_to_camera_view(scene, projection_camera, Vector(world))
        if point.z <= 0:
            raise ValueError("Camera registration points must remain in front of the camera")
        return [round(point.x * WIDTH, 6), round((1 - point.y) * HEIGHT, 6)]

    try:
        camera_frames = []
        for index in range(frame_count):
            progress = index / (frame_count - 1)
            camera_at(progress)
            # world_to_camera_view reads matrix_world; evaluate it explicitly
            # because assigning location alone leaves a stale projection matrix.
            bpy.context.view_layer.update()
            camera_frames.append({
                "src": f"/landing/floodguard-v2/camera/approach-{index:02}.webp",
                "at": round(progress, 6),
                "projection": [projected(point) for point in world_triangle],
                "projectionDiagnostics": [projected(probe["world"]) for probe in diagnostics],
            })
        close_anchors = anchors()
    finally:
        scene.camera = source_camera
        bpy.data.objects.remove(projection_camera, do_unlink=True)
        bpy.data.cameras.remove(projection_data)
        bpy.context.view_layer.update()

    manifest = {"version": 2, "width": WIDTH, "height": HEIGHT, "delivery": "Blender-rendered 3D with HTML and 2D portraits",
                "cameraFrames": camera_frames,
                "cameraRegistration": {
                    "space": "native-image-pixels", "origin": "top-left",
                    "worldTriangle": world_triangle,
                    "worldUnits": "metres", "planeHeight": 1,
                    "meaning": "Affine correspondence on an illustrative ground plane; not geographic coordinates.",
                    "limitation": "Perspective and elevated roof geometry retain residual parallax; this is not a full 3D reprojection.",
                    "diagnosticProbes": diagnostics,
                },
                "closeStates": {state: f"/landing/floodguard-v2/plates/{state.lower()}.webp" for state in WATER_LEVELS},
                "anchors": close_anchors, "waterLevels": WATER_LEVELS,
                "notice": "Invented illustrative neighborhood. Water scenarios are not a forecast, road closure or official warning."}
    (PUBLIC / "scene-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    return manifest


def build():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    build_ground()
    build_roads()
    build_architecture()
    build_landscape()
    build_water()
    lighting()
    data = bpy.data.cameras.new("Drone_to_neighborhood_camera")
    camera = bpy.data.objects.new(data.name, data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera_at(1)
    finish_scene()
    render_settings()
    write_manifest()
    SOURCE.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / "floodguard-neighborhood.blend"), compress=True)
    mesh_objects = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    stats = {"meshObjects": len(mesh_objects), "vertices": sum(len(o.data.vertices) for o in mesh_objects),
             "faces": sum(len(o.data.polygons) for o in mesh_objects), "materials": len(bpy.data.materials),
             "houses": 26, "clinics": 1, "seed": 41127, "blender": bpy.app.version_string}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scene-statistics.json").write_text(json.dumps(stats, indent=2) + "\n", encoding="utf8")
    print("FLOODGUARD_SCENE", json.dumps(stats), flush=True)


def render(name, width, samples):
    render_settings(samples, width)
    path = OUT / "renders" / (name + ".png")
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    expected_camera = tuple(bpy.context.scene.camera.location)
    expected_water = bpy.data.objects["Controllable_water_surface"].location.z
    bpy.ops.render.render(write_still=True)
    assert tuple(bpy.context.scene.camera.location) == expected_camera, "Camera animation overrode a render job"
    assert bpy.data.objects["Controllable_water_surface"].location.z == expected_water, "Water animation overrode a render job"
    receipt = {"render": name, "camera": expected_camera, "water": expected_water, "width": width, "samples": samples}
    (path.parent / (name + ".json")).write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf8")
    print("FLOODGUARD_RENDER", str(path), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--load", action="store_true")
    parser.add_argument("--mode", choices=("build", "probe", "camera", "states", "export", "production"), default="probe")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--end", type=int, default=16)
    parser.add_argument("--width", type=int, default=1536)
    parser.add_argument("--samples", type=int, default=48)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [])
    if args.load:
        bpy.ops.wm.open_mainfile(filepath=str(SOURCE / "floodguard-neighborhood.blend"))
        finish_scene()
        if args.mode == "build":
            render_settings()
            bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / "floodguard-neighborhood.blend"), compress=True)
    else:
        build()
    water = bpy.data.objects["Controllable_water_surface"]
    if args.mode == "production":
        render_settings(96, 3072)
        bpy.ops.wm.save_as_mainfile(filepath=str(SOURCE / "floodguard-neighborhood.blend"), compress=True)
    if args.mode in ("probe", "camera", "states", "production"):
        # Keep animation in the saved source, but make each still an explicit shot.
        bpy.context.scene.camera.animation_data_clear()
        water.animation_data_clear()
    if args.mode == "probe":
        camera_at(1)
        render("probe-close", 1152, 24)
        camera_at(0)
        render("probe-wide", 1152, 24)
        camera_at(1)
        water.location.z = WATER_LEVELS["W2"]
        render("probe-flooded", 1152, 24)
    elif args.mode == "camera":
        water.location.z = WATER_LEVELS["W0"]
        for i in range(args.start, args.end):
            camera_at(i / 15)
            render(f"approach-{i:02}", args.width, args.samples)
    elif args.mode == "states":
        camera_at(1)
        for state, level in WATER_LEVELS.items():
            water.location.z = level
            render(state.lower(), args.width, args.samples)
    elif args.mode == "production":
        camera_at(1)
        for state, level in WATER_LEVELS.items():
            water.location.z = level
            render(state.lower(), 3072, 96)
        water.location.z = WATER_LEVELS["W0"]
        for i in range(16):
            camera_at(i / 15)
            render(f"approach-{i:02}", 2048 if i in (0, 15) else 1536, 48)
    elif args.mode == "export":
        water.location.z = WATER_LEVELS["W0"]
        bpy.ops.export_scene.gltf(filepath=str(SOURCE / "floodguard-neighborhood.glb"), export_format="GLB", export_cameras=True, export_lights=False, export_extras=True)
    write_manifest()


if __name__ == "__main__":
    main()
