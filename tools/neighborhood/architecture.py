"""Editable, metre-scale northern Thai neighbourhood architecture for Blender.

Front facades face local -Y. A returned Empty owns every generated mesh; changing
its transform moves the complete asset without changing the scene or camera.
Small repeated architectural parts are collected by material rather than added
as thousands of separate Blender objects. No external libraries are required.
"""

import math
import random

import bpy
from mathutils import Vector


def _material(name, color, roughness=0.75, texture=0.0, metallic=0.0):
    key = "FG_" + name
    existing = bpy.data.materials.get(key)
    if existing:
        return existing
    material = bpy.data.materials.new(key)
    material.diffuse_color = (*color, 1)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    principled = nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*color, 1)
    principled.inputs["Roughness"].default_value = roughness
    principled.inputs["Metallic"].default_value = metallic
    if texture:
        coords = nodes.new("ShaderNodeTexCoord")
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 7.5 if texture < 0.05 else 3.0
        noise.inputs["Detail"].default_value = 3.0
        noise.inputs["Roughness"].default_value = 0.65
        links.new(coords.outputs["Object"], noise.inputs["Vector"])
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.16
        ramp.color_ramp.elements[0].color = (*(c * 0.74 for c in color), 1)
        ramp.color_ramp.elements[1].position = 0.88
        ramp.color_ramp.elements[1].color = (*(min(1, c * 1.10) for c in color), 1)
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], principled.inputs["Base Color"])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.18
        bump.inputs["Distance"].default_value = texture
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    return material


def _palette(variant, clinic=False):
    walls = [(0.76, 0.68, 0.53), (0.81, 0.77, 0.64), (0.68, 0.68, 0.56),
             (0.77, 0.64, 0.49), (0.70, 0.73, 0.68)]
    roof_sets = [(0.37, 0.17, 0.085), (0.225, 0.29, 0.305),
                 (0.44, 0.25, 0.14), (0.285, 0.295, 0.28)]
    roof = (0.19, 0.34, 0.35) if clinic else roof_sets[variant % len(roof_sets)]
    result = {
        "wall": _material("ClinicLimewash" if clinic else f"Limewash{variant % 5}",
                          (0.83, 0.81, 0.70) if clinic else walls[variant % 5], texture=0.022),
        "stone": _material("FoundationStone", (0.38, 0.37, 0.32), texture=0.065),
        "trim": _material("WarmPlasterTrim", (0.87, 0.82, 0.68), texture=0.013),
        "wood": _material("AgedTeak", (0.21, 0.12, 0.065), texture=0.024),
        "woodlight": _material("OiledTeak", (0.35, 0.235, 0.12), texture=0.018),
        "dark": _material("RecessShadow", (0.055, 0.065, 0.06)),
        "glass": _material("SmokyBlueGlass", (0.16, 0.265, 0.285), roughness=0.24, metallic=0.22),
        "metal": _material("DarkBronzeMetal", (0.16, 0.18, 0.17), roughness=0.38, metallic=0.65),
        "paving": _material("PorchLimestone", (0.63, 0.61, 0.51), texture=0.035),
        "cross": _material("ClinicTeal", (0.065, 0.34, 0.35), roughness=0.6),
        "linen": _material("InteriorLinen", (0.71, 0.68, 0.54), roughness=0.95),
    }
    for i, factor in enumerate((0.87, 0.96, 1.045, 1.13)):
        result[f"tile{i}"] = _material(
            f"{'Clinic' if clinic else variant % 4}RoofTile{i}",
            tuple(c * factor for c in roof), roughness=0.7, texture=0.016)
    return result


class _Meshes:
    def __init__(self, root, materials):
        self.root = root
        self.materials = materials
        self.parts = {}

    def mesh(self, material, vertices, faces):
        verts, polys = self.parts.setdefault(material, ([], []))
        start = len(verts)
        verts.extend(tuple(v) for v in vertices)
        polys.extend(tuple(start + index for index in face) for face in faces)

    def box(self, material, center, size, angle=0):
        x, y, z = center
        a, b, c = (s / 2 for s in size)
        cs, sn = math.cos(angle), math.sin(angle)
        vertices = [(x + u * cs - v * sn, y + u * sn + v * cs, z + w)
                    for u, v, w in ((-a, -b, -c), (a, -b, -c), (a, b, -c), (-a, b, -c),
                                    (-a, -b, c), (a, -b, c), (a, b, c), (-a, b, c))]
        self.mesh(material, vertices, [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5),
                                      (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])

    def beam(self, material, start, end, width, depth=None):
        start, end = Vector(start), Vector(end)
        axis = (end - start).normalized()
        reference = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((0, 1, 0))
        u = axis.cross(reference).normalized() * width / 2
        v = axis.cross(u).normalized() * (depth or width) / 2
        vertices = [p + su * u + sv * v for p in (start, end)
                    for su, sv in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
        self.mesh(material, vertices, [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5),
                                      (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])

    def cylinder(self, material, start, end, radius, sides=10):
        start, end = Vector(start), Vector(end)
        axis = (end - start).normalized()
        reference = Vector((0, 0, 1)) if abs(axis.z) < 0.9 else Vector((0, 1, 0))
        u = axis.cross(reference).normalized()
        v = axis.cross(u).normalized()
        vertices = [p + radius * (u * math.cos(i * math.tau / sides) +
                                  v * math.sin(i * math.tau / sides))
                    for p in (start, end) for i in range(sides)]
        faces = [tuple(reversed(range(sides))), tuple(range(sides, sides * 2))]
        faces.extend((i, (i + 1) % sides, (i + 1) % sides + sides, i + sides)
                     for i in range(sides))
        self.mesh(material, vertices, faces)

    def finish(self):
        for material, (vertices, faces) in self.parts.items():
            mesh = bpy.data.meshes.new(f"{self.root.name}_{material}_Mesh")
            mesh.from_pydata(vertices, [], faces)
            mesh.materials.append(self.materials[material])
            mesh.update()
            obj = bpy.data.objects.new(f"{self.root.name}_{material}", mesh)
            bpy.context.collection.objects.link(obj)
            obj.parent = self.root
            if material in ("wall", "stone", "trim", "paving", "wood", "woodlight"):
                bevel = obj.modifiers.new("Small crafted edges", "BEVEL")
                bevel.width = 0.025 if material in ("wall", "stone", "paving") else 0.012
                bevel.segments = 2
                bevel.limit_method = "ANGLE"
                bevel.angle_limit = 0.55
        self.root["geometry_objects"] = len(self.parts)
        self.root["mesh_vertices"] = sum(len(v) for v, _ in self.parts.values())
        self.root["mesh_faces"] = sum(len(f) for _, f in self.parts.values())


def _root(name, location, rotation, scale, kind):
    root = bpy.data.objects.new(name, None)
    root.empty_display_type = "CUBE"
    root.empty_display_size = 0.4
    bpy.context.collection.objects.link(root)
    root.location = location
    root.rotation_euler.z = rotation
    root.scale = (scale, scale, scale)
    root["asset_type"] = kind
    root["units"] = "metres"
    root["front"] = "local -Y"
    return root


def _facade_point(u, y, z, angle):
    cs, sn = math.cos(angle), math.sin(angle)
    return (u * cs - y * sn, u * sn + y * cs, z)


def _front_box(mesh, material, u, y, z, width, depth, height, angle=0):
    mesh.box(material, _facade_point(u, y, z, angle), (width, depth, height), angle)


def _window(mesh, u, y, z, width=1.30, height=1.55, angle=0, shutters=False):
    # Dark reveal, glass set behind projecting casings, then a timber sash.
    for material, depth, w, h in (("dark", 0.045, width + 0.22, height + 0.20),
                                  ("glass", 0.075, width, height)):
        _front_box(mesh, material, u, y - depth, z, w, 0.035, h, angle)
    for offset in (-width / 2 - 0.055, width / 2 + 0.055):
        _front_box(mesh, "wood", u + offset, y - 0.115, z, 0.105, 0.14, height + 0.25, angle)
    for offset in (-height / 2 - 0.04, height / 2 + 0.05):
        _front_box(mesh, "wood", u, y - 0.115, z + offset, width + 0.22, 0.14, 0.10, angle)
    _front_box(mesh, "woodlight", u, y - 0.15, z, 0.055, 0.095, height, angle)
    _front_box(mesh, "woodlight", u, y - 0.15, z + height * 0.13, width, 0.095, 0.050, angle)
    _front_box(mesh, "trim", u, y - 0.20, z - height / 2 - 0.12,
               width + 0.40, 0.44, 0.14, angle)
    if shutters:
        for side in (-1, 1):
            su = u + side * (width * 0.72 + 0.16)
            sw = width * 0.39
            _front_box(mesh, "wood", su, y - 0.09, z, sw, 0.095, height + 0.11, angle)
            for row in range(12):
                _front_box(mesh, "woodlight", su, y - 0.15,
                           z - height * 0.43 + row * height * 0.078,
                           sw - 0.06, 0.06, 0.065, angle)
    # A narrow pale curtain edge adds depth without reflecting the whole facade.
    _front_box(mesh, "linen", u - width * 0.35, y - 0.093, z,
               width * 0.10, 0.01, height * 0.86, angle)


def _door(mesh, u, y, ground, width=1.35, angle=0, clinic=False):
    height = 2.34
    _front_box(mesh, "dark", u, y - 0.03, ground + height / 2,
               width + 0.22, 0.05, height + 0.18, angle)
    _front_box(mesh, "glass" if clinic else "woodlight", u, y - 0.08,
               ground + height / 2, width, 0.08, height, angle)
    for offset in (-width / 2 - 0.05, 0, width / 2 + 0.05):
        _front_box(mesh, "wood", u + offset, y - 0.15, ground + height / 2,
                   0.085, 0.13, height + 0.14, angle)
    for elevation in (ground + 0.09, ground + 0.8, ground + 1.72, ground + height):
        _front_box(mesh, "wood", u, y - 0.15, elevation, width + 0.17, 0.13, 0.08, angle)
    _front_box(mesh, "metal", u + 0.13, y - 0.24, ground + 1.10, 0.035, 0.06, 0.30, angle)


def _roof(mesh, width, depth, eave, rise, rng, center=(0, 0), gable=False, tile_size=0.30):
    """Four pitched surfaces with individual convex overlapping clay tiles."""
    cx, cy = center
    ridge = width if gable else max(width - depth * 0.86, width * 0.24)
    peak = eave + rise
    # Sections run from each eave to the ridge, avoiding a pyramid silhouette.
    surfaces = [
        ((-width / 2, -depth / 2, eave), (width / 2, -depth / 2, eave),
         (-ridge / 2, 0, peak), (ridge / 2, 0, peak)),
        ((width / 2, depth / 2, eave), (-width / 2, depth / 2, eave),
         (ridge / 2, 0, peak), (-ridge / 2, 0, peak)),
    ]
    if not gable:
        surfaces += [
            ((width / 2, -depth / 2, eave), (width / 2, depth / 2, eave),
             (ridge / 2, 0, peak), (ridge / 2, 0, peak)),
            ((-width / 2, depth / 2, eave), (-width / 2, -depth / 2, eave),
             (-ridge / 2, 0, peak), (-ridge / 2, 0, peak)),
        ]
    for p0, p1, p2, p3 in surfaces:
        a, b, c, d = map(Vector, (p0, p1, p2, p3))
        offset = Vector((cx, cy, 0))
        mesh.mesh("wood", [a + offset, b + offset, d + offset, c + offset,
                           a + offset - Vector((0, 0, 0.13)), b + offset - Vector((0, 0, 0.13)),
                           d + offset - Vector((0, 0, 0.13)), c + offset - Vector((0, 0, 0.13))],
                  [(0, 1, 2, 3), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)])
        run = (((c + d) / 2) - ((a + b) / 2)).length
        rows = max(2, math.ceil(run / 0.34))
        for row in range(rows):
            v0 = row / rows
            v1 = min(1.0, (row + 1.11) / rows)
            left0, right0 = a.lerp(c, v0), b.lerp(d, v0)
            left1, right1 = a.lerp(c, v1), b.lerp(d, v1)
            count = max(1, math.ceil((right0 - left0).length / tile_size))
            for tile in range(count):
                verts = []
                for left, right, row_lift in ((left0, right0, 0.026), (left1, right1, 0.020)):
                    for column in range(4):
                        u = (tile + column / 3) / count
                        point = left.lerp(right, u) + offset
                        point.z += row_lift + 0.027 * math.sin(column / 3 * math.pi)
                        verts.append(point)
                # Visible rolled lip and thickness; top quads catch continuous light.
                verts += [v - Vector((0, 0, 0.034)) for v in verts]
                faces = [(i, i + 1, i + 5, i + 4) for i in range(3)]
                faces += [(0, 8, 9, 1), (1, 9, 10, 2), (2, 10, 11, 3),
                          (0, 4, 12, 8), (3, 11, 15, 7), (4, 7, 15, 12)]
                mesh.mesh(f"tile{rng.choices(range(4), weights=(1, 4, 5, 1))[0]}", verts, faces)
        mesh.beam("wood", a + offset - Vector((0, 0, 0.09)),
                  b + offset - Vector((0, 0, 0.09)), 0.18, 0.25)
    # Segmented rounded ridge tiles and hip caps remain readable at close range.
    cap_paths = [((-ridge / 2, 0, peak + 0.10), (ridge / 2, 0, peak + 0.10))]
    if not gable:
        cap_paths += [((sx * width / 2, sy * depth / 2, eave + 0.07),
                       (sx * ridge / 2, 0, peak + 0.11)) for sx in (-1, 1) for sy in (-1, 1)]
    for start, end in cap_paths:
        a, b = Vector(start) + Vector((cx, cy, 0)), Vector(end) + Vector((cx, cy, 0))
        count = max(1, math.ceil((b - a).length / 0.32))
        for i in range(count):
            mesh.cylinder("tile2", a.lerp(b, i / count), a.lerp(b, min(1, (i + 1.04) / count)),
                          0.13, sides=10)
    # Exposed under-eave rafters, modeled individually in the shared timber mesh.
    for side in (-1, 1):
        for i in range(math.floor(width / 0.55) + 1):
            x = -width / 2 + 0.18 + i * (width - 0.36) / max(1, math.floor(width / 0.55))
            mesh.beam("woodlight", (cx + x, cy + side * (depth / 2 - 0.70), eave + 0.13),
                      (cx + x, cy + side * (depth / 2 - 0.04), eave - 0.12), 0.095, 0.12)


def _railing(mesh, x0, x1, y, base, height=0.90):
    for z in (base + 0.16, base + height):
        mesh.beam("wood", (x0, y, z), (x1, y, z), 0.075, 0.095)
    count = max(2, math.ceil((x1 - x0) / 0.22))
    for index in range(count + 1):
        x = x0 + (x1 - x0) * index / count
        mesh.box("woodlight", (x, y, base + height / 2), (0.055, 0.065, height))
    for x in (x0, x1):
        mesh.box("wood", (x, y, base + height / 2), (0.13, 0.13, height + 0.10))
        mesh.box("woodlight", (x, y, base + height + 0.07), (0.20, 0.20, 0.08))


def _steps(mesh, x, y, width, elevation, count=4):
    for i in range(count):
        rise = elevation * (i + 1) / count
        mesh.box("paving", (x, y + i * 0.28, rise / 2), (width, 0.31, rise))


def build_house(name: str, location=(0, 0, 0), rotation: float = 0,
                scale: float = 1, variant: int = 0, hero: bool = False):
    """Build an editable two-storey 8 by 7 metre home, returning its parent Empty.

    ``rotation`` is radians around Z. Variants change proportions, palette,
    shutters and roof style deterministically; ``hero`` adds a generous balcony.
    """
    rng = random.Random(98231 + variant * 127)
    root = _root(name, location, rotation, scale, "Thai-inspired two-storey home")
    mesh = _Meshes(root, _palette(variant))
    width = 8.2 if hero else 7.5 + (variant % 3) * 0.38
    depth = 6.6 + (variant % 2) * 0.4
    floor, upper, eave = 0.64, 3.64, 6.63
    mesh.box("stone", (0, 0, 0.31), (width + 0.12, depth + 0.12, 0.62))
    mesh.box("wall", (0, 0, floor + 1.45), (width, depth, 2.90))
    mesh.box("wall", (0, 0, upper + 1.44), (width, depth, 2.88))
    for z, thickness in ((floor, 0.16), (upper, 0.20), (eave - 0.12, 0.18)):
        mesh.box("trim", (0, 0, z), (width + 0.16, depth + 0.16, thickness))
    for x in (-width / 2 + 0.09, width / 2 - 0.09):
        for y in (-depth / 2 + 0.09, depth / 2 - 0.09):
            mesh.box("trim", (x, y, 3.59), (0.26, 0.26, 5.90))
    for face in range(4):
        angle = face * math.pi / 2
        span = width if face % 2 == 0 else depth
        y = -(depth if face % 2 == 0 else width) / 2
        for x in (-span * 0.29, span * 0.29):
            _window(mesh, x, y, 2.13, width=1.26, height=1.43, angle=angle)
            _window(mesh, x, y, 5.07, width=1.38, height=1.55, angle=angle,
                    shutters=face == 0 and variant % 2 == 0)
        if face == 0:
            _door(mesh, 0, y, floor + 0.04, width=1.30)
            _door(mesh, 0, y, upper + 0.06, width=1.35)
        elif face == 2:
            _window(mesh, 0, y, 5.08, width=0.95, angle=angle)
    # Projecting veranda with timber decking, support columns and joinery.
    veranda_width = width * (0.81 if hero else 0.64)
    front = -depth / 2
    veranda_depth = 1.55
    mesh.box("paving", (0, front - veranda_depth / 2, floor - 0.12),
             (veranda_width + 0.48, veranda_depth + 0.14, 0.26))
    mesh.box("wood", (0, front - veranda_depth / 2, upper - 0.16),
             (veranda_width + 0.22, veranda_depth + 0.15, 0.24))
    for index in range(math.ceil(veranda_width / 0.15)):
        x = -veranda_width / 2 + 0.06 + index * 0.15
        mesh.box("woodlight", (x, front - veranda_depth / 2, upper - 0.014),
                 (0.141, veranda_depth, 0.055))
    outer_y = front - veranda_depth + 0.08
    for x in (-veranda_width / 2 + 0.08, veranda_width / 2 - 0.08):
        mesh.box("stone", (x, outer_y, floor + 0.15), (0.43, 0.43, 0.30))
        mesh.box("trim", (x, outer_y, (floor + upper) / 2), (0.25, 0.25, upper - floor))
        mesh.box("wood", (x, outer_y, (upper + eave - 0.4) / 2),
                 (0.18, 0.18, eave - 0.4 - upper))
        for direction in (-1, 1):
            mesh.beam("woodlight", (x, outer_y, upper - 0.7),
                      (x + direction * 0.48, outer_y, upper - 0.24), 0.10)
    _railing(mesh, -veranda_width / 2, veranda_width / 2, outer_y, upper)
    for x in (-veranda_width / 2, veranda_width / 2):
        mesh.beam("wood", (x, outer_y, upper + 0.9), (x, front, upper + 0.9), 0.09)
        for index in range(6):
            mesh.box("woodlight", (x, outer_y + index * 0.25, upper + 0.47), (0.055, 0.055, 0.86))
    _steps(mesh, 0, front - veranda_depth - 0.9, 1.8, floor, count=4)
    _roof(mesh, width + 1.40, depth + 1.35, eave, 2.42 if hero else 2.25,
          rng, gable=variant % 5 == 3, tile_size=0.28 if hero else 0.34)
    # Small hipped canopy shadows the balcony, matching the main tiled roof.
    _roof(mesh, veranda_width + 0.65, 2.15, eave - 0.42, 0.70,
          rng, center=(0, front - 0.66), tile_size=0.30)
    if variant % 5 == 3:
        for side in (-1, 1):
            x = side * width / 2
            mesh.mesh("wall", [(x, -depth / 2, eave), (x, depth / 2, eave), (x, 0, eave + 2.25)],
                      [(0, 1, 2)])
            for z in (eave + 0.55, eave + 0.73, eave + 0.91):
                mesh.box("wood", (x + side * 0.02, 0, z), (0.08, 0.75, 0.075))
    # Utility detail on rear: conduit, drain pipe, condenser and louvres.
    mesh.cylinder("metal", (width / 2 - 0.18, depth / 2 + 0.08, 0.32),
                  (width / 2 - 0.18, depth / 2 + 0.08, eave - 0.08), 0.048)
    mesh.box("trim", (-width * 0.24, depth / 2 + 0.25, 1.42), (0.97, 0.48, 0.64))
    for i in range(7):
        mesh.box("metal", (-width * 0.24, depth / 2 + 0.50, 1.18 + i * 0.075), (0.77, 0.03, 0.025))
    mesh.finish()
    root["footprint_m"] = (width, depth)
    root["roof_height_m"] = eave + (2.42 if hero else 2.25)
    root["variant"] = variant
    return root


def build_clinic(name: str, location=(0, 0, 0), rotation: float = 0,
                 scale: float = 1, hero: bool = True):
    """Build a 12 by 9 metre, two-storey clinic with porch and accessible ramp."""
    root = _root(name, location, rotation, scale, "Illustrative neighbourhood clinic")
    mesh = _Meshes(root, _palette(0, clinic=True))
    rng = random.Random(49821)
    width, depth, floor, upper, eave = 12.0, 9.0, 0.60, 3.75, 6.90
    mesh.box("stone", (0, 0, 0.28), (width + 0.22, depth + 0.22, 0.56))
    mesh.box("wall", (0, 0, (floor + eave) / 2), (width, depth, eave - floor))
    for z in (floor, upper, eave - 0.1):
        mesh.box("trim", (0, 0, z), (width + 0.24, depth + 0.24, 0.19))
    for face in range(4):
        angle = face * math.pi / 2
        span = width if face % 2 == 0 else depth
        y = -(depth if face % 2 == 0 else width) / 2
        positions = (-span * 0.34, -span * 0.18, span * 0.18, span * 0.34)
        for x in positions:
            _window(mesh, x, y, 2.13, width=1.18, height=1.57, angle=angle)
            _window(mesh, x, y, 5.30, width=1.18, height=1.75, angle=angle)
        if face:
            _window(mesh, 0, y, 5.30, width=1.18, height=1.75, angle=angle)
        for x in (-span / 2 + 0.13, span / 2 - 0.13):
            _front_box(mesh, "trim", x, y - 0.04, 3.66, 0.34, 0.20, 6.04, angle)
    front = -depth / 2
    _door(mesh, 0, front, floor, width=2.12, clinic=True)
    mesh.box("trim", (0, front - 0.105, 5.35), (2.02, 0.18, 1.88))
    mesh.box("cross", (0, front - 0.22, 5.35), (0.43, 0.16, 1.28))
    mesh.box("cross", (0, front - 0.22, 5.35), (1.28, 0.16, 0.43))
    # Covered waiting veranda with paired column bases and head capitals.
    porch_width, porch_depth = 5.6, 2.35
    mesh.box("paving", (0, front - porch_depth / 2, floor - 0.14),
             (porch_width + 0.4, porch_depth + 0.2, 0.28))
    for x in (-porch_width / 2 + 0.23, porch_width / 2 - 0.23):
        y = front - porch_depth + 0.18
        mesh.box("trim", (x, y, 2.10), (0.28, 0.28, 3.0))
        for z in (floor + 0.13, 3.51):
            mesh.box("trim", (x, y, z), (0.44, 0.44, 0.22))
    _roof(mesh, porch_width + 0.7, porch_depth + 0.72, 3.58, 0.83,
          rng, center=(0, front - porch_depth / 2 + 0.20), tile_size=0.29)
    _roof(mesh, width + 1.70, depth + 1.70, eave, 2.56, rng, tile_size=0.29 if hero else 0.35)
    _steps(mesh, 0, front - porch_depth - 0.86, 2.3, floor)
    # Ramp descends beside the steps; a real wedge instead of a floating slab.
    x0, x1, y0, y1 = 1.60, 5.60, front - porch_depth - 1.48, front - porch_depth - 0.12
    mesh.mesh("paving", [(x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0),
                         (x0, y0, floor), (x1, y0, 0.05), (x1, y1, 0.05), (x0, y1, floor)],
              [(0, 3, 2, 1), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7), (4, 5, 6, 7)])
    for y in (y0 + 0.1, y1 - 0.1):
        for i in range(5):
            x = x0 + i * (x1 - x0) / 4
            elevation = floor + (0.05 - floor) * i / 4
            mesh.cylinder("metal", (x, y, elevation), (x, y, elevation + 0.90), 0.029, sides=8)
        mesh.cylinder("metal", (x0, y, floor + 0.90), (x1, y, 0.95), 0.036, sides=10)
    # Waiting bench and subtle durable furniture under the canopy.
    for side in (-1, 1):
        x = side * 1.81
        mesh.box("woodlight", (x, front - 0.82, floor + 0.46), (1.10, 0.42, 0.095))
        mesh.box("woodlight", (x, front - 0.61, floor + 0.84), (1.10, 0.07, 0.52))
        for dx in (-0.39, 0.39):
            mesh.box("metal", (x + dx, front - 0.82, floor + 0.23), (0.06, 0.32, 0.46))
    mesh.finish()
    root["footprint_m"] = (width, depth)
    root["roof_height_m"] = eave + 2.56
    root["scope"] = "Illustrative preparedness scene; not an operational facility model"
    return root
