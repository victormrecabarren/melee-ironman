"""Add attachment points to existing damage atlases without rerendering them.

Uses the export's saved Blender actions and its original atlas projection.
Run with the bpy Python runtime. New exports write this data directly.
"""
import argparse
import json
import math
from pathlib import Path

from dat_assets import roots, fighter_bone_index
from scene_assets import u32


def run(args):
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector
    from PIL import Image

    path=args.output/'manifest.json'
    manifest=json.loads(path.read_text())
    roster={r['slug']:r['code'] for r in json.loads(Path(__file__).with_name('roster.json').read_text())}
    for key,fighter in manifest['fighters'].items():
        clips={k:c for k,c in fighter['clips'].items() if k in ('hit','recoil') and not c.get('damageAnchors')}
        if not clips:continue
        blend=args.data/'rendered'/f'{key}.blend'
        if key=='roy-left' and not blend.exists():blend=args.data/'rendered'/'roy.blend'
        bpy.ops.wm.open_mainfile(filepath=str(blend))
        if any(c['source'] not in bpy.data.actions for c in clips.values()):
            bpy.ops.wm.open_mainfile(filepath=str(blend)+'1')
        scene=bpy.context.scene
        armature=next(o for o in scene.objects if o.type=='ARMATURE')
        armature.rotation_euler.z=math.pi/2 if fighter['facing']=='right' else -math.pi/2
        scene.camera.data.ortho_scale=4.8*fighter.get('scale',1)
        code=fighter.get('code') or roster[key.removesuffix('-left')]
        data=(args.data/f'Pl{code}.dat').read_bytes()
        root=next(iter(roots(data).values()));table=32+u32(data,root+0x54)
        anchor=fighter.get('anchor',[256,330])
        origin=world_to_camera_view(scene,scene.camera,Vector((0,0,0)))
        offset=[anchor[0]-origin.x*512,anchor[1]-(1-origin.y)*384]
        for name,clip in clips.items():
            clip.setdefault('fps',manifest['fps'])
            action=bpy.data.actions[clip['source']]
            armature.animation_data.action=action
            armature.animation_data.action_slot=action.slots[0]
            anchors=[];centers=[]
            with Image.open(args.output/clip['file']) as atlas:
                for frame in range(clip['frames']):
                    scene.frame_set(frame*(60//clip['fps']))
                    points=[]
                    for slot in range(5):
                        bone_index=fighter_bone_index((args.data/'PlCo.dat').read_bytes(),fighter['kind'],u32(data,table+4*slot))
                        bone=next(b for b in armature.pose.bones if b.name.startswith('Bone_') and int(b.name[5:])==bone_index)
                        point=world_to_camera_view(scene,scene.camera,armature.matrix_world @ bone.matrix.translation)
                        points.append([round(point.x*512+offset[0],2),round((1-point.y)*384+offset[1],2)])
                    anchors.append(points)
                    x,y=frame%8*512,frame//8*384
                    box=atlas.crop((x,y,x+512,y+384)).getchannel('A').point(lambda a:255 if a>10 else 0).getbbox()
                    if not box:raise ValueError(f'{key}/{name}: blank frame {frame}')
                    centers.append([(box[0]+box[2])/2,(box[1]+box[3])/2])
            clip['damageAnchors']=anchors;clip['frameCenters']=centers
        print(f'Updated {key}',flush=True)
    path.write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args())
