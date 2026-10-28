"""Render original Final Destination/revival models and common impact effects.

Uses scene_assets.py and the pinned importer in pipeline.json. The GameCube
additive effect shader is approximated with a texture mask, then composited
with Canvas screen blending. This does not simulate Melee's particle engine.
"""
import argparse
import json
import math
import struct
import hashlib
import sys
from pathlib import Path
from scene_assets import import_model, stage_model, respawn_model, arrival_model, effect_model
from dat_assets import roots


def run(args):
    sys.path.insert(0, str(args.importer.resolve()))
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
    from PIL import Image
    work = args.data / 'rendered'
    work.mkdir(exist_ok=True)
    manifest_path = args.output / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    environment = manifest.get('environment', {})
    def clear_import_handlers():
        for handler in list(bpy.app.handlers.depsgraph_update_post):
            if hasattr(handler, '_dat_sync_armature'):
                bpy.app.handlers.depsgraph_update_post.remove(handler)

    for kind in args.only or ['stage', 'revival', 'arrival', 'impact', 'slash']:
        clear_import_handlers()
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if kind == 'stage':
            data = (args.data / 'GrNLa.dat').read_bytes()
            for index in [1, 2, 3]:
                import_model(data, *stage_model(data, index), name=f'fd{index}', max_frame=10)
            target, location, scale, size = (0, 0, -3), (0, -30, .6), 21, (2400, 1240)
            frames, fps = [4], 30
        elif kind == 'arrival':
            data = (args.data / 'PlCo.dat').read_bytes()
            import_model(data, *arrival_model(data), name='arrival', max_frame=1)
            target, location, scale, size = (0, 0, 0), (0, -10, 1.2), 2, (512, 256)
            frames, fps = [0], 60
        elif kind == 'revival':
            data = (args.data / 'PlCo.dat').read_bytes()
            import_model(data, *respawn_model(data), name='revival', max_frame=40)
            target, location, scale, size = (0, 0, 0), (0, -10, 1.2), 2, (512, 256)
            frames, fps = list(range(36)), 60
        else:
            data = (args.data / 'EfCoData.dat').read_bytes()
            spec, duration, _shape = effect_model(data, 9 if kind == 'impact' else 8)
            import_model(data, *spec, name=kind, max_frame=12)
            for obj in bpy.data.objects:
                if obj.type == 'MESH':
                    obj.hide_render = False
            # GX blending uses the source texture's intensity. The generic
            # importer otherwise makes its zero-intensity region solid blue.
            for material in bpy.data.materials:
                tree = material.node_tree
                texture = next(n for n in tree.nodes if n.type == 'TEX_IMAGE')
                emission = next(n for n in tree.nodes if n.type == 'EMISSION')
                source = emission.inputs['Color'].links[0].from_socket
                mask = tree.nodes.new('ShaderNodeMixRGB'); mask.blend_type = 'MULTIPLY'
                mask.inputs[0].default_value = 1
                tree.links.new(source, mask.inputs[1]); tree.links.new(texture.outputs['Color'], mask.inputs[2])
                tree.links.new(mask.outputs[0], emission.inputs['Color'])
                output = next(n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL')
                tree.links.new(emission.outputs[0], output.inputs['Surface'])
            target, location, scale, size = (0, 0, 0), (0, -10, 0), 7, (384, 384)
            frames, fps = list(range(0, math.ceil(duration), 2)), 30
        scene = bpy.context.scene
        target = Vector(target)
        bpy.ops.object.camera_add(location=location)
        camera = bpy.context.object
        camera.rotation_euler = (target-camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.type = 'ORTHO'; camera.data.ortho_scale = scale; scene.camera = camera
        for location in [(-6, -10, 12), (8, 2, 6)]:
            bpy.ops.object.light_add(type='AREA', location=location)
            light = bpy.context.object; light.data.energy = 3000 if kind == 'stage' else 300
            light.data.size = 8
            light.rotation_euler = (target-light.location).to_track_quat('-Z', 'Y').to_euler()
        scene.world = bpy.data.worlds.new('World'); scene.world.use_nodes = True
        background = scene.world.node_tree.nodes['Background']
        background.inputs['Color'].default_value = (0, 0, 0, 1) if kind in ['impact', 'slash'] else (.5, .5, .5, 1)
        background.inputs['Strength'].default_value = .7
        scene.render.engine = 'CYCLES'; scene.cycles.samples = 32; scene.cycles.use_denoising = True
        scene.render.resolution_x, scene.render.resolution_y = size; scene.render.resolution_percentage = 100
        scene.render.film_transparent = kind in ['stage', 'revival', 'arrival']
        scene.render.image_settings.file_format = 'PNG'; scene.render.image_settings.color_mode = 'RGBA'
        scene.view_settings.view_transform = 'AgX' if kind == 'stage' else 'Standard'
        scene.view_settings.exposure = -.5 if kind == 'stage' else 0
        columns = min(8, len(frames))
        atlas = Image.new('RGBA', (size[0]*columns, size[1]*math.ceil(len(frames)/columns)))
        for index, frame in enumerate(frames):
            scene.frame_set(frame)
            scene.render.filepath = str(work / f'{kind}.png')
            bpy.ops.render.render(write_still=True)
            with Image.open(scene.render.filepath) as image:
                atlas.paste(image, ((index % columns)*size[0], (index//columns)*size[1]))
        filename = f'{kind}.webp'
        atlas.save(args.output / filename, quality=92, method=6)
        # EntryStart raises the fighter by 1.497345 game units above the
        # pedestal origin (ft_0C31.c). Anchor its top to the same spawn height.
        origin = world_to_camera_view(scene, camera, Vector((0, 0, .1497345 if kind=='arrival' else 0)))
        environment[kind] = {'file': filename, 'width': size[0], 'height': size[1],
                             'columns': columns, 'frames': len(frames), 'fps': fps,
                             'anchor': [round(origin.x*size[0], 2), round((1-origin.y)*size[1], 2)]}
        if kind=='arrival':
            environment[kind]['source']={'file':'PlCo.dat','root':'ftLoadCommonData+0x40',
                'sha256':hashlib.sha256(data).hexdigest(),'topGameUnits':1.497345}
            # The entry code scales the pedestal separately from the fighter's
            # model_scale, using common attribute +0x110 (trophy_scale).
            for fighter in manifest['fighters'].values():
                fighter_data=(args.data / f"Pl{fighter['code']}.dat").read_bytes()
                attrs=32+struct.unpack_from('>I',fighter_data,next(iter(roots(fighter_data).values())))[0]
                value=struct.unpack_from('>f',fighter_data,attrs+0x110)[0]
                if not math.isfinite(value) or not .1<=value<=4:raise ValueError('Invalid trophy platform scale')
                fighter['arrivalPlatformScale']=value
        print('EXPORTED', kind, flush=True)
    clear_import_handlers()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    manifest['environment'] = environment
    manifest_path.write_text(json.dumps(manifest, indent=2)+'\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['importer', 'data', 'output']:
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--only', nargs='+')
    run(parser.parse_args())
