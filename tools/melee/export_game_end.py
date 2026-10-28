"""Export US Melee's original match-end model and announcer call.

ifStatus_802F7034 selects ScInfCnt_scene_models[5]. ifStatus_803F9628
selects SEM 510037 at overlay frame 8. The .usd archive is essential:
the same model in IfAll.dat says the Japanese-region 'Game Set'.
"""
import argparse,json,math,struct,sys,wave
from pathlib import Path
from scene_assets import roots,u32,import_model
from render_audio import read_bank,resolve_sem

def run(args):
    sys.path.insert(0,str(args.importer.resolve()))
    import bpy
    from mathutils import Vector
    from PIL import Image
    from compact_fighters import compact_clip
    data=(args.data/'IfAll.usd').read_bytes()
    is_go=args.kind=='go';kind='game-go' if is_go else 'game-end'
    model_index=4 if is_go else 5
    frame_count=40 if is_go else 12
    width,height=1008,560 if is_go else 360
    md=32+u32(data,roots(data)['ScInfCnt_scene_models']+model_index*4)
    j,a,m,shape=struct.unpack_from('>4I',data,md)
    if shape:raise ValueError('Unexpected shape animation')
    a=u32(data,32+a) if a else 0;m=u32(data,32+m) if m else 0
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import_model(data,j,a,m,name='game',max_frame=frame_count)
    scene=bpy.context.scene
    # HUD framing adapted to the canvas. Preserve the original joint motion,
    # texture, silhouette and transparency; no lettering is recreated.
    target=Vector((0,0,.13))
    bpy.ops.object.camera_add(location=(0,-10,.13));cam=bpy.context.object
    cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.type='PERSP';cam.data.angle=2*math.atan(5.6/20);scene.camera=cam
    scene.render.engine='CYCLES';scene.cycles.samples=8
    scene.render.resolution_x=width;scene.render.resolution_y=height;scene.render.resolution_percentage=100
    scene.render.film_transparent=True;scene.render.image_settings.color_mode='RGBA';scene.view_settings.view_transform='Standard'
    atlas=Image.new('RGBA',(width*4,height*math.ceil(frame_count/4)))
    for f in range(frame_count):
        scene.frame_set(f);scene.render.filepath=str(args.data/'rendered'/f'{kind}.png');bpy.ops.render.render(write_still=True)
        with Image.open(scene.render.filepath) as im:atlas.paste(im,((f%4)*width,(f//4)*height))
    args.output.mkdir(parents=True,exist_ok=True)
    filename=kind+'.webp';atlas.save(args.output/filename,lossless=True)
    clip={'file':filename,'width':width,'height':height,'columns':4,'frames':frame_count,'fps':60,'anchor':[width/2,height/2],
          'source':f'IfAll.usd: ScInfCnt_scene_models[{model_index}], original joint animation and material',
          'announcerDelayFrames':10 if is_go else 8,'appearAfterKoFrames':0}
    clip=compact_clip(args.output,clip,width,height,4)
    sound_id=510039 if is_go else 510037;sample_id=resolve_sem((args.data/'smash2.sem').read_bytes(),sound_id)
    rate,channels=read_bank(args.data/'nr_name.ssm')[sample_id]
    length=min(map(len,channels));samples=[channels[c][i] for i in range(length) for c in range(len(channels))]
    sound_name='go-announcer' if is_go else 'game-announcer'
    with wave.open(str(args.output/(sound_name+'.wav')),'wb') as w:
        w.setnchannels(len(channels));w.setsampwidth(2);w.setframerate(rate);w.writeframes(struct.pack('<'+'h'*len(samples),*samples))
    path=args.output/'manifest.json';manifest=json.loads(path.read_text())
    manifest['environment'][kind]=clip
    manifest['audio'][sound_name]={'file':sound_name+'.wav','soundId':sound_id,'sampleId':sample_id,'duration':length/rate,'source':'audio/us/nr_name.ssm via audio/us/smash2.sem'}
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    print('EXPORTED original US',kind,'overlay and announcer',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['data','output','importer']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--kind',choices=['game','go'],default='game')
    run(p.parse_args())
