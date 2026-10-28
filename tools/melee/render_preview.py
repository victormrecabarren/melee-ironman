"""Render Dr. Mario and Roy's original animations into transparent sprite atlases.

Requires Python 3.11, bpy==4.5.7, Pillow, and StarsMmd's importer at
commit dc71de837978a6a2fe8c5082f2840cfafb135235. See pipeline.json.
Example:
  python tools/melee/render_preview.py --importer /path/to/importer --data /path/to/dat --output public/melee-preview
"""
import argparse
import json
import math
import sys
from pathlib import Path

from accessory_dynamics import bake as bake_accessory_dynamics
from fighter_setup import model_scale, apply_gamewatch, VERSION as SCALE_VERSION
from combat_geometry import sample_geometry
from smash_sequence import read_preview_move, combine_animations
from move_data import read_action
from sword_trail import SwordTrail
from dat_assets import animations, animation_set, visibility, apply_visibility, fighter_bone_index
from scene_assets import install_tev_alpha_fix, roots, u32
from fighter_materials import apply as apply_fighter_materials, MATERIAL_VERSION
import taunt_props


def run(args):
    sys.path.insert(0, str(args.importer.resolve()))
    import bpy
    from mathutils import Vector
    from PIL import Image
    from importer.phases.route.route import route_sections
    from importer.phases.parse.parse import parse_sections
    from importer.phases.describe.describe import describe_scene
    from importer.phases.plan.plan import plan_scene
    from importer.phases.build_blender.build_blender import build_blender_scene
    from importer.phases.post_process.post_process import post_process
    install_tev_alpha_fix()
    from animation_scaling import install as install_joint_scale_fix
    install_joint_scale_fix()

    args.output.mkdir(parents=True, exist_ok=True)
    work = args.data / 'rendered'
    work.mkdir(exist_ok=True)
    common = (args.data/'PlCo.dat').read_bytes()
    manifest = {'fps': 30, 'width': 512, 'height': 384, 'columns': 8, 'fighters': {}}
    manifest_path = args.output / 'manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
    specs = json.loads(Path(__file__).with_name('roster.json').read_text())
    specs += [{'code':'Nn','slug':'nana','name':'Nana','kind':11}]
    for spec in specs:
        code, slug, title = spec['code'], spec['slug'], spec['name']
        if args.fighter and args.fighter != code: continue
        animation_code='Pp' if code=='Nn' else code
        names=[name for name,_,_ in animations(args.data / f'Pl{animation_code}AJ.dat')]
        smash=next((name for name in ['AttackS4S','AttackS4','AttackS41'] if name in names),None)
        if not smash: raise ValueError(f'{title}: missing forward smash')
        move = read_preview_move(args.data / f'Pl{animation_code}.dat', smash)
        taunt_source=next(n for n in ([('AppealL' if args.facing=='left' else 'AppealR'),'Appeal','AppealR']) if n in names)
        taunt=read_action(args.data/f'Pl{animation_code}.dat',taunt_source)
        if args.facing == 'left': slug += '-left'
        if args.fighter and args.fighter != code:
            continue
        bpy.ops.wm.read_factory_settings(use_empty=True)
        options = {'game': 'SMASH_BROS', 'filepath': f'Pl{code}Nr.dat', 'section_names': [], 'max_frame': 600}
        data = (args.data / f'Pl{code}Nr.dat').read_bytes()
        sections = parse_sections(data, route_sections(data, game='SMASH_BROS'), options)
        ir = describe_scene(sections, options)
        model = ir.models[0]
        joint = next(s.root_node for s in sections if s.section_name.endswith('_Share_joint'))
        apply_visibility(model, joint, visibility((args.data / f'Pl{code}.dat').read_bytes(), code))
        clips = {('Wait1' if 'Wait1' in names else 'Wait'): 'idle', 'Fall': 'fall', 'Landing': 'landing', smash: 'smash',
                 'DamageFlyN': 'hit', 'DamageN3': 'recoil', 'DamageFlyRoll': 'tumble', taunt_source:'taunt'}
        if args.clips:
            clips = {source: clip for source, clip in clips.items() if clip in args.clips}
            # Geometry needs both source actions, even for a smash-only refresh.
            if 'smash' in args.clips:
                clips['Wait1' if 'Wait1' in names else 'Wait'] = 'idle'
        durations = {}
        model.bone_animations = []
        sequence_parts = {}
        for name, data, root in animations(args.data / f'Pl{animation_code}AJ.dat'):
            if 'smash' in clips.values() and 'sequence' in move and name in ('AttackS41','AttackS42'):
                sequence_parts[name] = animation_set(name, data, root, model.bones)
                continue
            if name in clips:
                animation, duration = animation_set(name, data, root, model.bones)
                if name == 'DamageFlyRoll':
                    from shared.IR.animation import IRKeyframe
                    from shared.IR.enums import Interpolation
                    common = (args.data/'PlCo.dat').read_bytes()
                    table = 32+u32(common, roots(common)['ftLoadCommonData']+0x10)
                    parts = 32+u32(common, table+spec['kind']*4)
                    xrot = common[32+u32(common, parts+4)+2]
                    # ftCo_Damage.c doFlyRoll: facing * atan2(vx, vy).
                    # Both fighters face their attacker, hence -atan2(|vx|,vy).
                    # Match previewCamera.js: dy/dx=.2-.064*p along the eased path.
                    animation.tracks[xrot].rotation[0] = [IRKeyframe(
                        frame=f, value=-math.atan2(1, .2-.064*(1-math.exp(-2.3*min(1,f/(60*.9))))/(1-math.exp(-2.3))),
                        interpolation=Interpolation.LINEAR) for f in range(math.ceil(duration)+1)]
                model.bone_animations.append(animation)
                durations[name] = duration
        if sequence_parts:
            animation, duration = combine_animations(sequence_parts, move)
            del clips[smash]
            clips[animation.name] = 'smash'
            model.bone_animations.append(animation)
            durations[animation.name] = duration
        if set(durations) != set(clips):
            raise ValueError(f'Missing animations: {set(clips) - set(durations)}')
        dynamics_audit=bake_accessory_dynamics(model,(args.data/f'Pl{code}.dat').read_bytes(),common,spec['kind'],code)
        built = build_blender_scene(plan_scene(ir, options), bpy.context, options)
        post_process(set(), options=options, build_results=built)
        material_audit=apply_fighter_materials(model,f'Pl{code}Nr')
        armature = built[0]['armature']
        # Render each fighter from its real side of the matchup, so Roy's
        # front/back and sword hand remain correct (no mirrored sword hand).
        armature.rotation_euler.z = math.pi / 2 if args.facing == 'right' else -math.pi / 2
        gamewatch_setup=apply_gamewatch(model,armature,(args.data/'PlGw.dat').read_bytes()) if code=='Gw' else None
        scene = bpy.context.scene
        target = Vector((0, 0, 1.3))
        bpy.ops.object.camera_add(location=(0, -10, 2.5))
        camera = bpy.context.object
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
        camera.data.type = 'ORTHO'
        camera.data.ortho_scale = {'Kp':9.4,'Pr':7.8}.get(code,6.8)
        scene.camera = camera
        for location, power, size in [((-3, -4, 6), 500, 5), ((3, 1, 4), 300, 4)]:
            bpy.ops.object.light_add(type='AREA', location=location)
            light = bpy.context.object
            light.data.energy, light.data.size = power, size
            light.rotation_euler = (target - light.location).to_track_quat('-Z', 'Y').to_euler()
        scene.world = bpy.data.worlds.new('World')
        scene.world.use_nodes = True
        background = scene.world.node_tree.nodes['Background']
        background.inputs['Color'].default_value = (.5, .5, .5, 1)
        background.inputs['Strength'].default_value = .6
        scene.render.engine = args.engine
        scene.cycles.samples = 16
        scene.render.threads_mode = 'FIXED'
        scene.render.threads = 4
        scene.render.use_persistent_data = True
        scene.cycles.use_denoising = True
        scene.render.resolution_x, scene.render.resolution_y = 512, 384
        scene.render.resolution_percentage = 100
        scene.render.film_transparent = True
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGBA'
        scene.view_settings.view_transform = 'Standard'
        scene.render.fps = 60
        prop=taunt_props.build(code,(args.data/f'Pl{code}.dat').read_bytes(),common,spec['kind'],args.facing,armature,model.bones,taunt) if 'taunt' in clips.values() else None
        if prop:taunt['propSource']=prop['source']
        armature.animation_data.action = built[0]['actions'][0]
        bpy.ops.wm.save_as_mainfile(filepath=str(work / f'{slug}.blend'))
        existing = manifest['fighters'].get(slug, {}).get('clips', {}) if args.clips else {}
        if args.clips and 'smash' not in args.clips:
            move = manifest['fighters'].get(slug, {}).get('move', move)
        fighter = {**(manifest['fighters'].get(slug, {}) if args.clips else {}),
                   'name': title, 'facing': args.facing, 'kind':spec['kind'], 'code':code, 'scale':camera.data.ortho_scale/4.8, 'pipelineVersion':2, 'clips': dict(existing), 'move': move}
        if dynamics_audit:
            dynamics_audit['clips']={**fighter.get('accessoryDynamics',{}).get('clips',{}),**dynamics_audit['clips']}
            fighter['accessoryDynamics']=dynamics_audit
        fighter['modelScale']=model_scale((args.data/f'Pl{code}.dat').read_bytes())
        fighter['modelScaleVersion']=SCALE_VERSION
        if gamewatch_setup: fighter['specialSetup']=gamewatch_setup
        fighter['materialVersion']=(MATERIAL_VERSION if not args.clips or
            manifest['fighters'].get(slug,{}).get('materialVersion')==MATERIAL_VERSION else 'mixed; full material refresh required')
        fighter['materialAudit']=material_audit
        fighter['taunt']=taunt
        from bpy_extras.object_utils import world_to_camera_view
        origin=world_to_camera_view(scene,camera,Vector((0,0,0)))
        fighter['anchor']=[round(origin.x*512,2),round((1-origin.y)*384,2)]
        for action in built[0]['actions']:
            clip = clips[action.name]
            if args.clips and clip not in args.clips: continue
            armature.animation_data.action = action
            armature.animation_data.action_slot = action.slots[0]
            fps = 60 if clip in ('smash', 'tumble') else 30
            frames = list(range(0, max(2, math.ceil(durations[action.name])), 60 // fps))
            trail = SwordTrail(armature, model.bones, move['trail']) if clip == 'smash' and 'trail' in move else None
            attachments = []
            commands=taunt if clip=='taunt' else move
            if code=='Gw' and clip not in ('smash','taunt'):
                commands=read_action(args.data/'PlGw.dat',action.name)
            damage_anchors = []
            if args.test_frame:
                frames = [args.test_frame]
            atlas = Image.new('RGBA', (512 * 8, 384 * math.ceil(len(frames) / 8)))
            previews = []
            clipping=[]
            for index, frame in enumerate(frames):
                scene.frame_set(frame)
                overrides={}
                if clip in ('smash','taunt') or code=='Gw':
                    for event in commands['events']:
                        if event['frame'] <= frame and event['opcode']==31:
                            overrides[event['fields']['Struct ID']]=event['fields']['Object ID']
                apply_visibility(model,joint,visibility((args.data/f'Pl{code}.dat').read_bytes(),code,overrides))
                digits=len(str(max(len(model.meshes)-1,0)))
                for mesh_index,mesh in enumerate(model.meshes):
                    obj=bpy.data.objects[f'Pl{code}Nr_mesh_{mesh_index:0{digits}}']
                    obj.hide_render=mesh.is_hidden
                if trail:
                    trail.update(scene, frame)
                taunt_props.update(prop,frame,clip=='taunt')
                if clip in ('hit', 'recoil', 'tumble'):
                    from bpy_extras.object_utils import world_to_camera_view
                    fighter_data=(args.data/f'Pl{code}.dat').read_bytes()
                    root=next(iter(roots(fighter_data).values()))
                    table=32+u32(fighter_data,root+0x54)
                    points=[]
                    for slot in range(5):
                        bone=armature.pose.bones[model.bones[fighter_bone_index(common,spec['kind'],u32(fighter_data,table+4*slot))].name]
                        point=world_to_camera_view(scene,camera,armature.matrix_world @ bone.matrix.translation)
                        points.append([round(point.x*512,2),round((1-point.y)*384,2)])
                    damage_anchors.append(points)
                if clip in ('smash','taunt'):
                    from bpy_extras.object_utils import world_to_camera_view
                    anchors = {}
                    for event in commands['events']:
                        if event['opcode'] != 10:
                            continue
                        fields = event['fields']; bone = armature.pose.bones[model.bones[fighter_bone_index(common,spec['kind'],fields['Bone ID'])].name]
                        offset = Vector((fields['Z'], fields['Y'], fields['X'])) * (.1 / 256)
                        point = world_to_camera_view(scene, camera, armature.matrix_world @ bone.matrix @ offset)
                        anchors[str(fields['GFX ID'])] = [round(point.x * 512, 2), round((1-point.y) * 384, 2)]
                    attachments.append(anchors)
                scene.render.filepath = str(work / f'{slug}-{clip}.png')
                bpy.ops.render.render(write_still=True)
                with Image.open(scene.render.filepath) as rendered:
                    image = rendered.copy()
                atlas.paste(image, ((index % 8) * 512, (index // 8) * 384))
                previews.append(image)
                box=image.getchannel('A').point(lambda a:255 if a>10 else 0).getbbox()
                if not box or box[0]<2 or box[1]<2 or box[2]>510 or box[3]>382: clipping.append(frame)
            filename = f'{slug}-{clip}.webp'
            atlas.save(args.output / filename, 'WEBP', quality=88, method=6)
            if clip in ('idle', 'smash'):
                previews[0].save(work / f'{slug}-{clip}-animated.webp', save_all=True,
                                 append_images=previews[1:], duration=1000 // fps, loop=0,
                                 quality=88, method=4)
            fighter['clips'][clip] = {'file': filename, 'frames': len(frames),
                                     'duration': len(frames) / fps, 'fps': fps, 'source': action.name, 'clippedFrames':clipping}
            if clip == 'smash':
                fighter['move']['attachments'] = attachments
            if clip == 'taunt':
                fighter['taunt']['attachments'] = attachments
                fighter['taunt']['fps'] = fps
            if clip in ('hit', 'recoil', 'tumble'):
                fighter['clips'][clip]['damageAnchors']=damage_anchors
                fighter['clips'][clip]['frameCenters'] = [
                    [(box[0]+box[2])/2, (box[1]+box[3])/2]
                    for image in previews
                    for box in [image.getchannel('A').point(lambda alpha: 255 if alpha > 10 else 0).getbbox()]]
                if clip == 'tumble':
                    fighter['clips'][clip]['runtimeRotation']='ftCo_Damage.c doFlyRoll / PlCo part_to_joint[2]'
            if trail:
                bpy.data.objects.remove(trail.obj, do_unlink=True)
            print(f'EXPORTED {title}: {clip}, {len(frames)} frames', flush=True)
        if not args.clips or 'smash' in args.clips:
            fighter['combatGeometry']=sample_geometry(scene,armature,model,fighter,(args.data/f'Pl{code}.dat').read_bytes(),common)
        elif not {'idle','smash'}.intersection(args.clips) and manifest['fighters'].get(slug,{}).get('combatGeometry'):
            fighter['combatGeometry']=manifest['fighters'][slug]['combatGeometry']
        manifest['fighters'][slug] = fighter
        manifest_path.write_text(json.dumps(manifest, indent=2) + '\n')
        # Clear cross-armature item constraints before Blender tears down its
        # datablocks; the standalone bpy runtime otherwise crashes on exit.
        if prop:
            for obj in prop['objects']:
                if obj.type=='ARMATURE':
                    for bone in obj.pose.bones:
                        for constraint in list(bone.constraints):bone.constraints.remove(constraint)
    for handler in list(bpy.app.handlers.depsgraph_update_post):
        if hasattr(handler,'_dat_sync_armature'):bpy.app.handlers.depsgraph_update_post.remove(handler)
    bpy.ops.wm.read_factory_settings(use_empty=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--importer', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--fighter')
    parser.add_argument('--facing',choices=['right','left'],default='right')
    parser.add_argument('--engine',default='CYCLES')
    parser.add_argument('--test-frame', type=int)
    parser.add_argument('--clips', nargs='+', choices=['idle', 'fall', 'landing', 'smash', 'hit', 'recoil', 'tumble','taunt'])
    run(parser.parse_args())
