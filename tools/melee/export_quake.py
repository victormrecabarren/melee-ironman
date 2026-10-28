"""Sample Final Destination's original large KO camera shake (22 frames)."""
import argparse,json,sys
from pathlib import Path
from dat_assets import roots
from scene_assets import import_model,u32

def run(args):
    sys.path.insert(0,str(args.importer.resolve()))
    import bpy
    data=(args.data/'GrNLa.dat').read_bytes()
    root=roots(data)['quake_model_set']
    animation=u32(data,32+u32(data,root+4)+3*4)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    built=import_model(data,u32(data,root),animation,name='large-quake',max_frame=22)
    armature=built[0]['armature'];action=built[0]['actions'][0]
    armature.animation_data.action=action;armature.animation_data.action_slot=action.slots[0]
    samples=[]
    for frame in range(22):
        bpy.context.scene.frame_set(frame)
        # Importer maps game XYZ to Blender XZY and scales by 0.1.
        point=armature.pose.bones[0].matrix.translation
        samples.append([round(point.x*10,6),round(point.z*10,6)])
    path=args.output/'manifest.json';manifest=json.loads(path.read_text())
    manifest['common']['koQuake']={'source':'GrNLa.dat: quake_model_set.anims[3]; grLib_801C9CEC / Camera_RequestQuake','fps':60,'offsets':samples}
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    print(samples)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['data','output','importer']:p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
