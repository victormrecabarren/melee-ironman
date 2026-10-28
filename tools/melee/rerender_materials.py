"""Refresh installed fighter lighting without changing motion or framing.

Reads saved source scenes and DAT materials. Each fighter is staged completely
before its manifest references switch to versioned atlases. Original atlases
remain available for rollback. No roster entries are added by this command.
"""
import argparse,json,math,sys,time
from pathlib import Path
from fighter_materials import apply, MATERIAL_VERSION
from dat_assets import roots,visibility,apply_visibility
from sword_trail import SwordTrail

def run(args):
    sys.path.insert(0,str(args.importer.resolve()))
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
    from PIL import Image
    from importer.phases.route.route import route_sections
    from importer.phases.parse.parse import parse_sections
    from importer.phases.describe.describe import describe_scene
    prefs=bpy.context.preferences.addons['cycles'].preferences
    if args.device=='METAL':
        prefs.compute_device_type='METAL';prefs.refresh_devices()
        for device in prefs.devices:device.use=device.type=='METAL'
        if not any(d.use for d in prefs.devices):raise ValueError('Metal device unavailable')
    path=args.output/'manifest.json';initial=json.loads(path.read_text())
    roster={r['slug']:r['code'] for r in json.loads(Path(__file__).with_name('roster.json').read_text())}
    keys=args.keys or list(initial['fighters']);status={}
    for key in keys:
        manifest=json.loads(path.read_text());fighter=manifest['fighters'][key]
        if fighter.get('materialVersion')==MATERIAL_VERSION:continue
        code=fighter.get('code') or roster[key.removesuffix('-left')]
        options={'game':'SMASH_BROS','filepath':f'Pl{code}Nr.dat','section_names':[],'max_frame':600}
        data=(args.data/f'Pl{code}Nr.dat').read_bytes()
        sections=parse_sections(data,route_sections(data,game='SMASH_BROS'),options)
        model=describe_scene(sections,options).models[0]
        joint=next(s.root_node for s in sections if s.section_name.endswith('_Share_joint'))
        move=fighter['move'];fighter_data=(args.data/f'Pl{code}.dat').read_bytes()
        scene_path=args.data/'rendered'/f'{key}.blend'
        if key=='roy-left' and not scene_path.exists():scene_path=args.data/'rendered'/'roy.blend'
        bpy.ops.wm.open_mainfile(filepath=str(scene_path))
        sources={c['source'] for c in fighter['clips'].values()}
        if not sources.issubset(bpy.data.actions.keys()):bpy.ops.wm.open_mainfile(filepath=str(scene_path)+'1')
        if not sources.issubset(bpy.data.actions.keys()):raise ValueError(f'{key}: missing saved actions {sources-set(bpy.data.actions.keys())}')
        scene=bpy.context.scene;arm=next(o for o in scene.objects if o.type=='ARMATURE')
        arm.rotation_euler.z=math.pi/2 if fighter['facing']=='right' else -math.pi/2
        camera=scene.camera;camera.data.ortho_scale=4.8*fighter.get('scale',1)
        origin=world_to_camera_view(scene,camera,Vector((0,0,0)));anchor=fighter.get('anchor',[256,330])
        right=camera.rotation_euler.to_quaternion()@Vector((1,0,0));up=camera.rotation_euler.to_quaternion()@Vector((0,1,0))
        camera.location+=right*(origin.x-anchor[0]/512)*camera.data.ortho_scale
        camera.location+=up*(origin.y-(1-anchor[1]/384))*camera.data.ortho_scale*384/512
        audit=apply(model,f'Pl{code}Nr')
        scene.render.engine='CYCLES';scene.cycles.device='GPU' if args.device=='METAL' else 'CPU'
        scene.cycles.samples=16;scene.cycles.use_denoising=True;scene.render.use_persistent_data=True
        scene.render.threads_mode='FIXED';scene.render.threads=4
        scene.render.resolution_x=512;scene.render.resolution_y=384;scene.render.resolution_percentage=100
        dest=args.staging/key;dest.mkdir(parents=True,exist_ok=True)
        clips={};digits=len(str(max(len(model.meshes)-1,0)));start=time.time()
        for kind,clip in fighter['clips'].items():
            action=bpy.data.actions[clip['source']];arm.animation_data.action=action;arm.animation_data.action_slot=action.slots[0]
            trail=SwordTrail(arm,model.bones,move['trail']) if kind=='smash' and 'trail' in move else None
            atlas=Image.new('RGBA',(512*8,384*math.ceil(clip['frames']/8)))
            for index in range(clip['frames']):
                source_frame=index*60/clip.get('fps',manifest['fps']);scene.frame_set(int(source_frame),subframe=source_frame%1)
                overrides={}
                if kind=='smash':
                    for event in move['events']:
                        if event['frame']<=source_frame and event['opcode']==31:overrides[event['fields']['Struct ID']]=event['fields']['Object ID']
                apply_visibility(model,joint,visibility(fighter_data,code,overrides))
                for i,mesh in enumerate(model.meshes):bpy.data.objects[f'Pl{code}Nr_mesh_{i:0{digits}}'].hide_render=mesh.is_hidden
                if trail:
                    if not source_frame.is_integer():raise ValueError('Sword afterimage requires whole game frames')
                    trail.update(scene,int(source_frame))
                scene.render.filepath=str(dest/'frame.png');bpy.ops.render.render(write_still=True)
                with Image.open(dest/'frame.png') as im:
                    box=im.getchannel('A').point(lambda a:255 if a>10 else 0).getbbox()
                    if not box:raise ValueError(f'{key}/{kind}/{index}: blank frame')
                    if box[0]<2 or box[1]<2 or box[2]>510 or box[3]>382:
                        # Legacy strips can already touch the canvas (Roy's sword
                        # trail). Preserve their framing, but reject new clipping.
                        baseline=(args.baseline or args.output)/clip['file']
                        with Image.open(baseline) as old:
                            x=index%8*512;y=index//8*384
                            old_box=old.crop((x,y,x+512,y+384)).getchannel('A').point(lambda a:255 if a>10 else 0).getbbox()
                        if not old_box or any(abs(a-b)>2 for a,b in zip(box,old_box)):
                            raise ValueError(f'{key}/{kind}/{index}: new clipped frame {box}, before {old_box}')
                        print('EXISTING_EDGE_CONTACT',key,kind,index,box,flush=True)
                    atlas.paste(im,(index%8*512,index//8*384))
                if index%30==0:print('PROGRESS',key,kind,index,clip['frames'],flush=True)
            filename=clip['file'].removesuffix('.webp')+'-materials-v1.webp'
            atlas.save(dest/filename,quality=88,method=6)
            clips[kind]={**clip,'file':filename}
            if trail:bpy.data.objects.remove(trail.obj,do_unlink=True)
        # Publish only a complete fighter; reread to preserve concurrent unrelated edits.
        for clip in clips.values():(args.output/clip['file']).write_bytes((dest/clip['file']).read_bytes())
        current=json.loads(path.read_text())
        original_files={kind:c['file'] for kind,c in fighter['clips'].items()}
        for alias,value in current['fighters'].items():
            if {kind:c['file'] for kind,c in value['clips'].items()}==original_files:
                value['clips']={kind:{**c,'file':clips[kind]['file']} for kind,c in value['clips'].items()}
                value['materialVersion']=MATERIAL_VERSION;value['materialAudit']=audit
        temp=path.with_suffix('.materials.tmp');temp.write_text(json.dumps(current,indent=2)+'\n');temp.replace(path)
        status[key]={'seconds':round(time.time()-start),'frames':sum(c['frames'] for c in clips.values())}
        (args.staging/'status.json').write_text(json.dumps(status,indent=2)+'\n')
        print('PUBLISHED',key,status[key],flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['importer','data','output','staging']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--baseline',type=Path,help='Original installed atlases for detecting new edge clipping')
    p.add_argument('--keys',nargs='+');p.add_argument('--device',choices=['CPU','METAL'],default='CPU');run(p.parse_args())
