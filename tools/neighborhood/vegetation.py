"""Editable, deterministic vegetation for the FloodGuard neighborhood master.

The plants use tapered branch meshes and individually shaped leaves.  Each
plant is parented to a local Empty, so callers can move, scale, duplicate, or
export it without changing the scene, camera, lights, or render settings.
"""

from __future__ import annotations

import math
import random
from typing import Iterable, Sequence

import bpy
from mathutils import Vector


Vec3 = tuple[float, float, float]


class _Mesh:
    def __init__(self) -> None:
        self.vertices: list[tuple[float, float, float]] = []
        self.faces: list[tuple[int, ...]] = []
        self.material_indices: list[int] = []
        self.uvs: list[tuple[float, float]] = []

    def vertex(self, point: Vector, uv: tuple[float, float] = (0, 0)) -> int:
        self.vertices.append(tuple(point))
        self.uvs.append(uv)
        return len(self.vertices) - 1

    def face(self, points: Iterable[int], material: int = 0) -> None:
        self.faces.append(tuple(points))
        self.material_indices.append(material)

    def object(self, name: str, parent: bpy.types.Object,
               materials: Sequence[bpy.types.Material]) -> bpy.types.Object:
        mesh = bpy.data.meshes.new(name + "_Geometry")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        obj = bpy.data.objects.new(name, mesh)
        bpy.context.collection.objects.link(obj)
        obj.parent = parent
        for material in materials:
            mesh.materials.append(material)
        for polygon, material_index in zip(mesh.polygons, self.material_indices):
            polygon.material_index = material_index
            polygon.use_smooth = True
        uv_layer = mesh.uv_layers.new(name="LeafAndBarkUV")
        for loop in mesh.loops:
            uv_layer.data[loop.index].uv = self.uvs[loop.vertex_index]
        return obj


def _material(name: str, color: tuple[float, float, float, float],
              leaf: bool = False, bark: bool = False) -> bpy.types.Material:
    existing = bpy.data.materials.get(name)
    if existing:
        return existing
    material = bpy.data.materials.new(name)
    material.diffuse_color = color
    material.use_nodes = True
    tree = material.node_tree
    nodes, links = tree.nodes, tree.links
    shader = nodes.get("Principled BSDF")
    shader.inputs["Roughness"].default_value = .68 if leaf else .88
    shader.inputs["Specular IOR Level"].default_value = .25
    shader.inputs["Base Color"].default_value = color
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 8 if leaf else 4
    noise.inputs["Detail"].default_value = 3
    noise.inputs["Roughness"].default_value = .7
    if bark:
        mapping = nodes.new("ShaderNodeVectorMath")
        mapping.operation = "MULTIPLY"
        mapping.inputs[1].default_value = (15, 15, 1.25)
        links.new(coordinates.outputs["Object"], mapping.inputs[0])
        links.new(mapping.outputs[0], noise.inputs["Vector"])
    else:
        links.new(coordinates.outputs["Object"], noise.inputs["Vector"])
    variation = nodes.new("ShaderNodeValToRGB")
    variation.color_ramp.elements[0].position = .12
    variation.color_ramp.elements[0].color = tuple(c * .66 for c in color[:3]) + (1,)
    variation.color_ramp.elements[1].position = .87
    variation.color_ramp.elements[1].color = tuple(min(c * 1.23, 1) for c in color[:3]) + (1,)
    links.new(noise.outputs["Fac"], variation.inputs[0])
    links.new(variation.outputs["Color"], shader.inputs["Base Color"])
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = .2 if leaf else .38
    bump.inputs["Distance"].default_value = .012 if leaf else .045
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    if leaf:
        shader.inputs["Subsurface Weight"].default_value = .075
        shader.inputs["Subsurface Radius"].default_value = (.12, .2, .08)
        shader.inputs["Coat Weight"].default_value = .06
        shader.inputs["Coat Roughness"].default_value = .45
        # The per-leaf UVs keep the fine central vein attached to every leaf.
        separate = nodes.new("ShaderNodeSeparateXYZ")
        links.new(coordinates.outputs["UV"], separate.inputs[0])
        subtract = nodes.new("ShaderNodeMath")
        subtract.operation = "SUBTRACT"
        subtract.inputs[1].default_value = .5
        links.new(separate.outputs["X"], subtract.inputs[0])
        absolute = nodes.new("ShaderNodeMath")
        absolute.operation = "ABSOLUTE"
        links.new(subtract.outputs[0], absolute.inputs[0])
        vein = nodes.new("ShaderNodeMath")
        vein.operation = "LESS_THAN"
        vein.inputs[1].default_value = .018
        links.new(absolute.outputs[0], vein.inputs[0])
        mix = nodes.new("ShaderNodeMixRGB")
        links.new(vein.outputs[0], mix.inputs[0])
        links.new(variation.outputs["Color"], mix.inputs[1])
        mix.inputs[2].default_value = tuple(min(c * 1.55, 1) for c in color[:3]) + (1,)
        links.new(mix.outputs["Color"], shader.inputs["Base Color"])
    return material


def _palette() -> tuple[bpy.types.Material, list[bpy.types.Material]]:
    bark = _material("FG_Bark_Fissured_WarmGrey", (.16, .125, .083, 1), bark=True)
    leaves = [
        _material("FG_Leaf_Olive", (.205, .272, .087, 1), leaf=True),
        _material("FG_Leaf_Forest", (.108, .197, .067, 1), leaf=True),
        _material("FG_Leaf_Sunlit", (.292, .348, .121, 1), leaf=True),
        _material("FG_Leaf_Sage", (.218, .292, .151, 1), leaf=True),
        _material("FG_Leaf_Young", (.337, .382, .14, 1), leaf=True),
    ]
    return bark, leaves


def _root(name: str, location: Vec3, scale: float, kind: str, seed: int) -> bpy.types.Object:
    if scale <= 0:
        raise ValueError("Plant scale must be positive")
    root = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(root)
    root.empty_display_type = "PLAIN_AXES"
    root.empty_display_size = .4
    root.location = location
    root.scale = (scale,) * 3
    root["asset_kind"] = kind
    root["procedural_seed"] = seed
    root["geometry_description"] = "Editable tapered branches and individually curved leaf meshes"
    return root


def _basis(direction: Vector) -> tuple[Vector, Vector]:
    direction = direction.normalized()
    reference = Vector((0, 0, 1)) if abs(direction.z) < .92 else Vector((1, 0, 0))
    side = direction.cross(reference).normalized()
    return side, direction.cross(side).normalized()


def _tube(mesh: _Mesh, points: Sequence[Vector], radii: Sequence[float],
          sides: int = 7, material: int = 0) -> None:
    rings = []
    for index, (point, radius) in enumerate(zip(points, radii)):
        previous = points[max(index - 1, 0)]
        following = points[min(index + 1, len(points) - 1)]
        side, up = _basis(following - previous)
        ring = []
        for spoke in range(sides):
            angle = spoke * math.tau / sides
            offset = (math.cos(angle) * side + math.sin(angle) * up) * radius
            ring.append(mesh.vertex(point + offset, (spoke / sides, index / max(1, len(points) - 1))))
        rings.append(ring)
    for index in range(len(rings) - 1):
        for spoke in range(sides):
            next_spoke = (spoke + 1) % sides
            mesh.face((rings[index][spoke], rings[index][next_spoke],
                       rings[index + 1][next_spoke], rings[index + 1][spoke]), material)
    mesh.face(reversed(rings[0]), material)
    mesh.face(rings[-1], material)


def _branch(mesh: _Mesh, start: Vector, end: Vector, radius: float,
            rng: random.Random, sides: int = 7, steps: int = 6) -> list[Vector]:
    direction = end - start
    side, _ = _basis(direction)
    bend = rng.uniform(-.1, .1) * direction.length
    points = [start.lerp(end, t / steps) + side * math.sin(math.pi * t / steps) * bend
              + Vector((0, 0, math.sin(math.pi * t / steps) * direction.length * .075))
              for t in range(steps + 1)]
    radii = [max(.0025, radius * (1 - t / steps * .91)) for t in range(steps + 1)]
    _tube(mesh, points, radii, sides)
    return points


def _leaf(mesh: _Mesh, base: Vector, direction: Vector, length: float,
          width: float, normal: Vector, material: int, curvature: float = .13,
          stations: int = 5) -> None:
    along = direction.normalized()
    side = normal.cross(along)
    if side.length < .0001:
        side, _ = _basis(along)
    else:
        side.normalize()
    up = along.cross(side).normalized()
    rows = []
    for row in range(stations + 1):
        t = row / stations
        center = base + along * (length * t)
        center += up * (math.sin(math.pi * t) * curvature * length - t * t * length * .06)
        span = max(.003, math.sin(math.pi * t) ** .72 * width)
        indices = []
        for edge in (-1, 0, 1):
            point = center + side * (edge * span)
            point += up * (abs(edge) * math.sin(math.pi * t) * length * .055)
            indices.append(mesh.vertex(point, ((edge + 1) * .5, t)))
        rows.append(indices)
    for row in range(stations):
        for column in range(2):
            mesh.face((rows[row][column], rows[row + 1][column],
                       rows[row + 1][column + 1], rows[row][column + 1]), material)


def build_tree(name: str, location: Vec3 = (0, 0, 0), scale: float = 1,
               seed: int = 0, quality: str = "hero") -> bpy.types.Object:
    """Build a 6–9 m broadleaf tree with visible forks and individually curved leaves.

    ``quality='background'`` retains the branch silhouette with fewer leaves.
    All dimensions are local metres before the root scale is applied.
    """
    if quality not in {"hero", "background"}:
        raise ValueError("quality must be 'hero' or 'background'")
    rng = random.Random(seed)
    root = _root(name, location, scale, "northern_thai_broadleaf_tree", seed)
    bark, palette = _palette()
    branches, foliage = _Mesh(), _Mesh()
    height = rng.uniform(6.4, 8.25)
    crown_radius = rng.uniform(2.05, 2.7)
    trunk_top = Vector((rng.uniform(-.2, .2), rng.uniform(-.2, .2), height * .75))
    trunk_points = [Vector((0, 0, 0)), Vector((-.04, .04, .45)),
                    Vector((.08, -.025, height * .19)),
                    Vector((-.1, .065, height * .37)),
                    Vector((.02, .12, height * .58)), trunk_top]
    _tube(branches, trunk_points, [.28, .22, .19, .15, .105, .035], 12)
    # Surface roots merge into the trunk without a cylindrical stump silhouette.
    for index in range(7):
        angle = index * math.tau / 7 + rng.uniform(-.2, .2)
        direction = Vector((math.cos(angle), math.sin(angle), 0))
        _tube(branches, [direction * .06 + Vector((0, 0, .29)),
                         direction * .23 + Vector((0, 0, .09)),
                         direction * .45 + Vector((0, 0, .02)),
                         direction * rng.uniform(.6, .77) + Vector((0, 0, -.025))],
              [.12, .085, .037, .003], sides=8)
    limbs = 13 if quality == "hero" else 11
    secondary_count = 4 if quality == "hero" else 3
    twig_count = 6 if quality == "hero" else 5
    pair_count = 10 if quality == "hero" else 8
    leaf_count = 0
    for limb in range(limbs):
        angle = limb * 2.399963 + rng.uniform(-.28, .28)
        radial = Vector((math.cos(angle), math.sin(angle), 0))
        tangent = Vector((-math.sin(angle), math.cos(angle), 0))
        inner_crown = limb >= int(limbs * .65)
        start = Vector((0, .07, height * (.35 + .31 * limb / max(1, limbs - 1))))
        end = radial * crown_radius * rng.uniform(.18 if inner_crown else .6,
                                                  .5 if inner_crown else .82)
        end.z = height * rng.uniform(.85 if inner_crown else .68,
                                     .96 if inner_crown else .83)
        _branch(branches, start, end, rng.uniform(.085, .125), rng, sides=9)
        for secondary in range(secondary_count):
            fraction = .43 + .56 * secondary / max(1, secondary_count - 1)
            junction = start.lerp(end, fraction)
            destination = end + tangent * rng.uniform(-.74, .74)
            destination += radial * rng.uniform(-.1, .55)
            destination.z += rng.uniform(-.08, .66)
            _branch(branches, junction, destination, .036, rng)
            for twig_index in range(twig_count):
                twig_angle = angle + rng.uniform(-1.45, 1.45)
                twig_start = junction.lerp(destination, .32 + twig_index * .12)
                twig_end = destination + Vector((math.cos(twig_angle) * rng.uniform(.25, .7),
                                                  math.sin(twig_angle) * rng.uniform(.25, .7),
                                                  rng.uniform(-.28, .55)))
                path = _branch(branches, twig_start, twig_end, .011, rng, sides=5, steps=4)
                axis = (twig_end - twig_start).normalized()
                side, up = _basis(axis)
                leaf_rotation = rng.uniform(0, math.tau)
                for pair in range(pair_count):
                    t = .14 + .85 * pair / max(1, pair_count - 1)
                    stem_point = twig_start.lerp(twig_end, t)
                    stem_point += Vector((0, 0, math.sin(math.pi * t) * .04))
                    # Spiral phyllotaxis avoids flat, repetitive rows of leaves.
                    leaf_angle = leaf_rotation + pair * 2.399963 + rng.uniform(-.3, .3)
                    leaf_side = side * math.cos(leaf_angle) + up * math.sin(leaf_angle)
                    for sign in (-1, 1):
                        direction = axis * .4 + leaf_side * sign * rng.uniform(.65, 1.1)
                        direction += up * rng.uniform(-.2, .35)
                        length = rng.uniform(.26, .43) * (1 - .22 * t)
                        normal = Vector((rng.uniform(-.5, .5), rng.uniform(-.5, .5), rng.uniform(.6, 1)))
                        _leaf(foliage, stem_point, direction, length, length * rng.uniform(.23, .34),
                              normal, rng.choices(range(5), weights=[32, 25, 20, 17, 6])[0],
                              stations=5 if quality == "hero" else 3)
                        leaf_count += 1
                _leaf(foliage, path[-1], axis, .22, .07, Vector((0, 0, 1)), 4,
                      stations=5 if quality == "hero" else 3)
                leaf_count += 1
    _Mesh.object(branches, name + "_Trunk_Branches_Roots", root, [bark])
    _Mesh.object(foliage, name + "_Curved_Leaves", root, palette)
    root["leaf_count"] = leaf_count
    root["quality"] = quality
    root["design_height_metres"] = round(height, 3)
    return root


def build_banana(name: str, location: Vec3 = (0, 0, 0), scale: float = 1,
                 seed: int = 0) -> bpy.types.Object:
    """Build a banana clump with layered pseudostems, curved blades, and split edges."""
    rng = random.Random(seed)
    root = _root(name, location, scale, "banana_clump", seed)
    _, palette = _palette()
    stems, blades = _Mesh(), _Mesh()
    stem_material = _material("FG_Banana_Pseudostem", (.285, .339, .124, 1), bark=True)
    sheath_material = _material("FG_Banana_Dry_Sheath", (.32, .238, .108, 1), bark=True)
    blade_material = _material("FG_Banana_Blade", (.207, .339, .099, 1), leaf=True)
    blade_young = _material("FG_Banana_Young_Blade", (.325, .429, .146, 1), leaf=True)
    blade_materials = [blade_material, palette[0], blade_young, sheath_material]
    for plant in range(3):
        offset = Vector((0, 0, 0)) if plant == 0 else Vector((rng.uniform(-.5, .5), rng.uniform(-.5, .5), 0))
        height = rng.uniform(1.8, 2.4) if plant == 0 else rng.uniform(.85, 1.55)
        radius = .105 if plant == 0 else .067
        tilt = Vector((rng.uniform(-.11, .11), rng.uniform(-.11, .11), 0))
        points = [offset + Vector((0, 0, height * t / 7)) + tilt * (t / 7) ** 2 for t in range(8)]
        _tube(stems, points, [radius * (1 - t / 11) for t in range(8)], sides=12)
        # Longitudinal overlapping sheaths remain editable geometry.
        for sheath in range(5):
            angle = sheath * math.tau / 5
            side = Vector((math.cos(angle), math.sin(angle), 0))
            _tube(stems, [offset + side * radius,
                          offset + side * (radius * .93) + Vector((0, 0, height * .35)),
                          offset + side * (radius * .64) + Vector((0, 0, height * .72))],
                  [.012, .009, .002], sides=4, material=1 if sheath % 3 == 0 else 0)
        leaf_total = 9 if plant == 0 else 6
        for leaf_index in range(leaf_total):
            angle = leaf_index * 2.399963 + rng.uniform(-.14, .14)
            outward = Vector((math.cos(angle), math.sin(angle), 0))
            side = Vector((-math.sin(angle), math.cos(angle), 0))
            length = rng.uniform(1.35, 2.25) * (height / 2.2)
            width = length * rng.uniform(.17, .235)
            start = points[-1] + Vector((0, 0, -.24 + leaf_index * .055))
            arch = rng.uniform(.45, .8)
            droop = rng.uniform(.35, .7)
            petiole_length = length * .18
            base = start + outward * petiole_length + Vector((0, 0, .17))
            _tube(stems, [start, start.lerp(base, .5) + Vector((0, 0, .055)), base],
                  [.022, .018, .012], sides=6)
            rows, centers = [], []
            subdivisions = 22
            material_index = 2 if leaf_index >= leaf_total - 2 else leaf_index % 2
            cuts = {rng.randint(6, subdivisions - 3): rng.uniform(.35, .72) for _ in range(4)}
            for row in range(subdivisions + 1):
                t = row / subdivisions
                center = base + outward * length * t
                center.z += arch * math.sin(math.pi * t * .8) - droop * t * t
                centers.append(center)
                span = max(.002, width * math.sin(math.pi * t) ** .68)
                indices = []
                for column in range(5):
                    lateral = (column - 2) / 2
                    split = cuts.get(row, 1) if column in (0, 4) else 1
                    point = center + side * span * lateral * split
                    point.z += abs(lateral) * .035 * math.sin(t * math.pi)
                    point.z += abs(lateral) * .026 * math.sin(t * math.pi * 16 + leaf_index)
                    point.z -= lateral * lateral * .07
                    indices.append(blades.vertex(point, (column / 4, t)))
                rows.append(indices)
            for row in range(subdivisions):
                for column in range(4):
                    blades.face((rows[row][column], rows[row + 1][column],
                                 rows[row + 1][column + 1], rows[row][column + 1]), material_index)
            _tube(stems, centers, [max(.001, .012 * (1 - row / subdivisions))
                                  for row in range(subdivisions + 1)], sides=5)
        # The rolled spear leaf gives the clump a recognizable growth point.
        tip = points[-1] + Vector((.04, -.04, height * .5))
        _tube(stems, [points[-1], points[-1].lerp(tip, .5), tip], [.035, .023, .002], sides=8)
    stems.object(name + "_Pseudostems_Petioles_Midribs", root, [stem_material, sheath_material])
    blades.object(name + "_Arching_Split_Leaf_Blades", root, blade_materials)
    return root


def build_shrub(name: str, location: Vec3 = (0, 0, 0), scale: float = 1,
                seed: int = 0) -> bpy.types.Object:
    """Build an informal garden shrub with twig structure and small curved leaves."""
    rng = random.Random(seed)
    root = _root(name, location, scale, "garden_shrub", seed)
    bark, palette = _palette()
    branches, foliage = _Mesh(), _Mesh()
    leaf_count = 0
    for shoot in range(13):
        angle = shoot * 2.399963 + rng.uniform(-.25, .25)
        outward = Vector((math.cos(angle), math.sin(angle), 0))
        start = Vector((rng.uniform(-.12, .12), rng.uniform(-.12, .12), .02))
        end = outward * rng.uniform(.18, .55) + Vector((0, 0, rng.uniform(.5, 1.08)))
        _branch(branches, start, end, .018, rng, sides=6, steps=5)
        for twig_index in range(5):
            t = .25 + twig_index * .14
            junction = start.lerp(end, t)
            twig_angle = angle + rng.uniform(-1.6, 1.6)
            twig_end = junction + Vector((math.cos(twig_angle) * .24,
                                           math.sin(twig_angle) * .24, rng.uniform(.03, .24)))
            _branch(branches, junction, twig_end, .005, rng, sides=4, steps=3)
            axis = (twig_end - junction).normalized()
            side, _ = _basis(axis)
            for pair in range(5):
                base = junction.lerp(twig_end, .16 + pair * .2)
                for sign in (-1, 1):
                    direction = axis * .5 + side * sign + Vector((0, 0, rng.uniform(-.2, .35)))
                    length = rng.uniform(.095, .165)
                    _leaf(foliage, base, direction, length, length * .32,
                          Vector((0, 0, 1)), rng.randrange(5), stations=4)
                    leaf_count += 1
    branches.object(name + "_Woody_Shoots", root, [bark])
    foliage.object(name + "_Curved_Leaves", root, palette)
    root["leaf_count"] = leaf_count
    return root
