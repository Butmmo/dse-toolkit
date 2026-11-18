"""Runs INSIDE Blender (blender -b -P blender_scene.py -- spec.json). Draws one Presence scene as 3D text under a slowly moving camera and renders it as a PNG sequence.
It is a plain script file the toolkit hands to Blender; it never runs in the normal Python. The spec is a JSON file written by dse/presence_blender.py:
  {width, height, frames, fps, out (a folder), engine, samples, bg, blocks: [{text, color, size, y, font, bold}], bar: {color, y, w} | null, move: "dolly" | "drift" | "still"}
Sizes and positions are in Blender units: the frame is 9 units wide. Nothing here reads a file other than the spec and a font file named in it, and nothing is sent anywhere."""
import json
import math
import sys

import bpy

spec = json.load(open(sys.argv[sys.argv.index("--") + 1], encoding="utf-8"))
W, H, FRAMES = int(spec["width"]), int(spec["height"]), max(1, int(spec["frames"]))


def rgb(hexv: str):
    c = hexv.lstrip("#")
    lin = lambda v: ((v / 255 + 0.055) / 1.055) ** 2.4 if v / 255 > 0.04045 else v / 255 / 12.92      # the colour as the kit says it, in Blender's linear space
    return tuple(lin(int(c[i:i + 2], 16)) for i in (0, 2, 4)) + (1.0,)


bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = W, H, 100
sc.render.fps = int(spec.get("fps", 24))
sc.frame_start, sc.frame_end = 1, FRAMES
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = spec["out"].rstrip("/\\") + "/f_"
sc.view_settings.view_transform = "Standard"                                                           # colours stay as the kit says them (no film look)

engine = spec.get("engine", "CYCLES")
try:
    sc.render.engine = engine
except TypeError:
    sc.render.engine = "CYCLES"
if sc.render.engine == "CYCLES":
    sc.cycles.device = "CPU"
    sc.cycles.samples = int(spec.get("samples", 24))
    sc.cycles.use_denoising = False

# the background is the world colour itself, so the page is exactly the kit's colour with no hot spots
world = bpy.data.worlds.new("w")
sc.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = rgb(spec["bg"])
world.node_tree.nodes["Background"].inputs[1].default_value = 1.0


def material(color):
    m = bpy.data.materials.new("m")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = rgb(color)
    b.inputs["Roughness"].default_value = 0.38
    return m


fonts = {}


def font(path):
    if not path:
        return None
    if path not in fonts:
        try:
            fonts[path] = bpy.data.fonts.load(path)
        except Exception:
            fonts[path] = None
    return fonts[path]


for b in spec["blocks"]:
    cu = bpy.data.curves.new("t", "FONT")
    cu.body = b["text"]
    cu.size = float(b["size"])
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    cu.extrude = float(b.get("depth", 0.07))
    cu.bevel_depth = 0.006
    cu.bevel_resolution = 2
    cu.space_line = 1.12
    f = font(b.get("font"))
    if f:
        cu.font = f
    ob = bpy.data.objects.new("t", cu)
    bpy.context.collection.objects.link(ob)
    ob.rotation_euler = (math.radians(90), 0, 0)                                                      # stand the text up so the camera, looking along +Y, reads it
    ob.location = (0, 0, float(b["y"]))
    ob.data.materials.append(material(b["color"]))

if spec.get("bar"):
    bar = spec["bar"]
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, float(bar["y"])))
    o = bpy.context.object
    o.scale = (float(bar["w"]), 0.12, 0.09)
    o.data.materials.append(material(bar["color"]))

# light: a soft key from the upper left and a wide fill, so the extrusion and the bevel catch the light
for name, loc, energy, size in (("key", (-4, -7, 7), 900, 6), ("fill", (4, -5, -1), 300, 8)):
    ld = bpy.data.lights.new(name, "AREA")
    ld.energy, ld.size = energy, size
    lo = bpy.data.objects.new(name, ld)
    bpy.context.collection.objects.link(lo)
    lo.location = loc
    lo.rotation_euler = (math.radians(80), 0, math.radians(-30 if name == "key" else 30))

cam_data = bpy.data.cameras.new("c")
cam_data.sensor_fit = "HORIZONTAL"
cam_data.lens = 50
cam_data.sensor_width = 36
cam = bpy.data.objects.new("c", cam_data)
bpy.context.collection.objects.link(cam)
sc.camera = cam
dist = 9 / (36 / 50)                                                                                   # at this distance the frame is 9 units wide
cam.rotation_euler = (math.radians(90), 0, 0)
move = spec.get("move", "dolly")
z0 = float(spec.get("cam_z", 0))
for fr in range(1, FRAMES + 1):
    t = (fr - 1) / max(1, FRAMES - 1)
    if move == "dolly":                                                                                # slowly closer, with a little sideways drift and tilt
        cam.location = (-0.25 + 0.5 * t, -dist * (1.0 - 0.07 * t), z0)
        cam.rotation_euler = (math.radians(90 + 1.2 * (0.5 - t)), 0, math.radians(1.6 * (0.5 - t)))
    elif move == "drift":
        cam.location = (-0.4 + 0.8 * t, -dist, z0 + 0.15 * math.sin(t * math.pi))
        cam.rotation_euler = (math.radians(90), 0, 0)
    else:
        cam.location = (0, -dist, z0)
    cam.keyframe_insert("location", frame=fr)
    cam.keyframe_insert("rotation_euler", frame=fr)

bpy.ops.render.render(animation=True)
