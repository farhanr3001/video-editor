"""Build pose-dependent, transparent views of a genuine 3D face prop.

Run from Blender, outside the shipped editor:
  blender -b -noaudio --factory-startup --python scripts/build_ar_views.py -- MODEL.glb OUTPUT_DIR

The editor loads these bounded-size views during preview/export. This keeps a
face prop's actual modeled side surfaces visible as the head turns without
loading a GPU scene or Blender on every timeline frame.
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


YAW_ANGLES = tuple(range(-60, 61, 6))
PITCH_ANGLES = (-20, -10, 0, 10, 20)
VIEW_SIZE = 512


def main():
    source, output = map(Path, sys.argv[sys.argv.index('--') + 1:sys.argv.index('--') + 3])
    source = source.resolve()
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH']
    # This Sketchfab AR source includes a 2-unit backdrop cube that is not
    # part of the wearable mask. Keep the filter asset, not its preview stage.
    for obj in meshes:
        if obj.name == 'Cube' and len(obj.data.vertices) == 8 and min(obj.dimensions) > 1:
            obj.hide_render = True
    meshes = [obj for obj in meshes if not obj.hide_render]
    if not meshes:
        raise RuntimeError('No renderable 3D meshes remain')
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    low = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    centre = (low + high) / 2
    span = high - low

    rig = bpy.data.objects.new('Face pose rig', None)
    bpy.context.scene.collection.objects.link(rig)
    for obj in meshes:
        world = obj.matrix_world.copy()
        obj.parent = rig
        obj.matrix_world = world

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 16
    scene.render.resolution_x = scene.render.resolution_y = VIEW_SIZE
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'Medium High Contrast'
    world = bpy.data.worlds.new('AR neutral studio')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 1.0
    scene.world = world

    cam_data = bpy.data.cameras.new('Front orthographic camera')
    cam = bpy.data.objects.new('Front orthographic camera', cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(span.x, span.z) * 1.22
    cam.location = Vector((0, -max(span) * 5, centre.z))
    cam.rotation_euler = (Vector((0, 0, centre.z)) - cam.location).to_track_quat('-Z', 'Y').to_euler()

    for label, location, energy in (
        ('key', (-1.0, -1.3, 1.5), 600),
        ('fill', (1.1, -1.0, .8), 500),
        ('rim', (.4, 1.2, 1.6), 750),
    ):
        lamp_data = bpy.data.lights.new(label, 'AREA')
        lamp_data.energy = energy
        lamp_data.shape = 'DISK'
        lamp_data.size = max(span) * 2
        lamp = bpy.data.objects.new(label, lamp_data)
        scene.collection.objects.link(lamp)
        lamp.location = Vector(location) * max(span) * 2
        lamp.rotation_euler = (centre - lamp.location).to_track_quat('-Z', 'Y').to_euler()

    for pitch in PITCH_ANGLES:
        for yaw in YAW_ANGLES:
            rig.rotation_euler = (math.radians(pitch), 0, math.radians(yaw))
            scene.render.filepath = str(output / f'y{yaw:+03d}_p{pitch:+03d}.png')
            bpy.ops.render.render(write_still=True)

    (output / 'views.json').write_text(json.dumps({
        'version': 1,
        'source': source.name,
        'yaw': YAW_ANGLES,
        'pitch': PITCH_ANGLES,
        'size': VIEW_SIZE,
        'model_bounds': {'min': list(low), 'max': list(high)},
    }, indent=2))


if __name__ == '__main__':
    main()
