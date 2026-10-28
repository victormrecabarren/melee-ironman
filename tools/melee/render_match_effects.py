"""Render IfAll's lupe HUD frame and EfCoData's real KO/dust animations."""
import argparse,json,math,sys
from pathlib import Path
from scene_assets import import_model,effect_model,roots,u32,has_shape_animation
from common_states import read_common


def run(args):
    sys.path.insert(0,str(args.importer.resolve()))
    import bpy
    from mathutils import Vector
    from bpy_extras.object_utils import world_to_camera_view
    from PIL import Image
    path=args.output/'manifest.json';manifest=json.loads(path.read_text());output=manifest['environment']
    for kind in args.only or ['magnifier','magnifier-mask','ko-p1','ko-p2','dust','landing-dust','smash-ground']:
        if kind=='normal-impact':raise ValueError('Model 10 contains particle emitters, not meshes. Use render_particles.py --only normal-impact.')
        for h in list(bpy.app.handlers.depsgraph_update_post):
            if hasattr(h,'_dat_sync_armature'):bpy.app.handlers.depsgraph_update_post.remove(h)
        bpy.ops.wm.read_factory_settings(use_empty=True)
        if kind.startswith('magnifier'):
            data=(args.data/'IfAll.dat').read_bytes();md=32+u32(data,roots(data)['lupe'])
            import_model(data,u32(data,md),name='lupe',max_frame=1)
            for obj in bpy.data.objects:
                if obj.type=='MESH':obj.hide_render=(obj.name=='lupe_mesh_2') if kind=='magnifier' else (obj.name!='lupe_mesh_2')
            if kind=='magnifier-mask':
                material=bpy.data.materials['lupe_mat_2'];tree=material.node_tree;tree.nodes.clear()
                emission=tree.nodes.new('ShaderNodeEmission');out=tree.nodes.new('ShaderNodeOutputMaterial');tree.links.new(emission.outputs[0],out.inputs['Surface'])
            scale,target,size,frames=1.4,(0,0,0),256,[0]
        else:
            index=25 if kind.startswith('ko') else {'arrival-glow':36,'landing-dust':24,'smash-ground':1,'dust':19,'normal-impact':10,'heavy-dust':20,'dash-dust':3,'kick-dust':5,'taunt-puff-dust':18,'taunt-ring-dust':4}[kind]
            data=bytearray((args.data/'EfCoData.dat').read_bytes());spec,duration,shape=effect_model(data,index)
            if kind.startswith('ko'):
                # efAsync 0x42B -> efLib_SetTevKonstColor on root's first child.
                # Player colors are runtime parameters from PlCo, not art edits.
                child=32+u32(data,32+spec[0]+8);dobj=32+u32(data,child+16)
                mobj=32+u32(data,dobj+8);tobj=32+u32(data,mobj+8);tev=32+u32(data,tobj+88)
                colors=read_common(args.data)['koColors'][0 if kind=='ko-p1' else 1]
                for offset,color in zip([16,20],colors):data[tev+offset:tev+offset+3]=bytes(color[:3])
            if has_shape_animation(data,shape):raise ValueError('Shape animation must be implemented for this effect')
            built=import_model(data,*spec,name=kind,max_frame=60)
            if kind=='dust':built[0]['armature'].rotation_euler.z=math.pi/2
            # Preserve the imported TEV color AND alpha chain. Bypassing alpha
            # makes the original effect quads visible as solid rectangles.
            # Keep pixels per world unit while padding the full dust trajectory.
            scale,target,size,frames=(80,(0,0,15),512,list(range(math.ceil(duration)))) if kind.startswith('ko') else (12,(0,0,.8),512,list(range(math.ceil(duration))))
        scene=bpy.context.scene;target=Vector(target)
        # Match the fighter export's downward view of effects on the floor.
        camera_height=9.6 if kind.endswith('dust') or kind in ['smash-ground','arrival-glow'] else 0
        bpy.ops.object.camera_add(location=(0,-80,target.z+camera_height));cam=bpy.context.object
        cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=scale;scene.camera=cam
        scene.world=bpy.data.worlds.new('World');scene.world.use_nodes=True;scene.world.node_tree.nodes['Background'].inputs['Color'].default_value=(0,0,0,1)
        if kind.endswith('dust') or kind=='smash-ground':
            for location in [(-3,-4,6),(3,1,4)]:
                bpy.ops.object.light_add(type='AREA',location=location);light=bpy.context.object
                light.data.energy=500;light.data.size=5
                light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
        scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True
        scene.render.resolution_x=scene.render.resolution_y=size;scene.render.resolution_percentage=100
        scene.render.film_transparent=kind.startswith('magnifier');scene.render.image_settings.color_mode='RGBA';scene.view_settings.view_transform='Standard'
        columns=min(8,len(frames));atlas=Image.new('RGBA',(size*columns,size*math.ceil(len(frames)/columns)))
        if args.probe:frames=[10]
        for frame_index,frame in enumerate(frames):
            scene.frame_set(frame);scene.render.filepath=str(args.data/'rendered'/f'{kind}.png');bpy.ops.render.render(write_still=True)
            with Image.open(scene.render.filepath) as image:atlas.paste(image,((frame_index%columns)*size,(frame_index//columns)*size))
        filename=kind+'.webp';atlas.save(args.output/filename,quality=92,method=6)
        origin=world_to_camera_view(scene,cam,Vector((0,0,0)))
        output[kind]={'file':filename,'width':size,'height':size,'columns':columns,'frames':len(frames),'fps':60,'anchor':[origin.x*size,(1-origin.y)*size],
            'source':'IfAll.dat: lupe' if kind.startswith('magnifier') else f'EfCoData.dat: model {index}'}
        if kind=='arrival-glow':output[kind]['pixelsPerGameUnit']=size/scale*.1
        print('EXPORTED',kind,flush=True)
    for h in list(bpy.app.handlers.depsgraph_update_post):
        if hasattr(h,'_dat_sync_armature'):bpy.app.handlers.depsgraph_update_post.remove(h)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    path.write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['data','output','importer']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--only',nargs='+');p.add_argument('--probe',action='store_true')
    run(p.parse_args())
