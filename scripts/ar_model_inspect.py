"""Render four diagnostic views of a candidate GLB in Blender.

Run with: blender -b -noaudio --factory-startup --python scripts/ar_model_inspect.py -- MODEL.glb OUTPUT_DIR
This is an asset-inspection tool, not part of Kinetic Cut's runtime.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


def main():
    source, output = map(Path, sys.argv[sys.argv.index('--') + 1:])
    output.mkdir(parents=True, exist_ok=True)
    bpy.ops.import_scene.gltf(filepath=str(source))
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == 'MESH'
              and not (obj.name == 'Cube' and len(obj.data.vertices) == 8)]
    if not meshes:
        raise RuntimeError('Model contains no meshes')
    for obj in meshes:
        print('AR_MODEL_MESH', obj.name, 'verts', len(obj.data.vertices),
              'dimensions', list(obj.dimensions), 'materials',
              [mat.name for mat in obj.data.materials], flush=True)
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj not in meshes:
            obj.hide_render = True
    bpy.context.view_layer.update()
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    low = Vector(tuple(min(p[i] for p in corners) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in corners) for i in range(3)))
    centre = (low + high) / 2
    span = high - low
    print('AR_MODEL_BOUNDS', list(low), list(high), 'mesh_count', len(meshes), flush=True)

    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 24
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.view_settings.view_transform = 'Standard'
    scene.view_settings.look = 'Medium High Contrast'
    world = bpy.data.worlds.new('AR inspection world')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = .55
    scene.world = world

    cam_data = bpy.data.cameras.new('Inspection camera')
    cam = bpy.data.objects.new('Inspection camera', cam_data)
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(span) * 1.55
    lamp_data = bpy.data.lights.new('Inspection softbox', 'AREA')
    lamp_data.energy = 450
    lamp_data.shape = 'DISK'
    lamp_data.size = max(span) * 1.5
    lamp = bpy.data.objects.new('Inspection softbox', lamp_data)
    scene.collection.objects.link(lamp)

    distance = max(span) * 3
    for label, direction in [('front_minus_y', Vector((0, -1, 0))),
                             ('back_plus_y', Vector((0, 1, 0))),
                             ('right_plus_x', Vector((1, 0, 0))),
                             ('left_minus_x', Vector((-1, 0, 0)))]:
        cam.location = centre + direction * distance
        cam.rotation_euler = (centre - cam.location).to_track_quat('-Z', 'Y').to_euler()
        lamp.location = centre + (direction + Vector((-.6, 0, .8))).normalized() * distance
        lamp.rotation_euler = (centre - lamp.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(output / f'{label}.png')
        bpy.ops.render.render(write_still=True)


if __name__ == '__main__':
    main()
