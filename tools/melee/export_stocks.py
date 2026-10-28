"""Extract the real stock portraits and 10-frame loss motion from IfAll.dat.

ifStock_802F8298 advances the icon's joint animation 1..10 and emits gfx 0x474
(common generator 247). gm_80168B34 selects neutral costume texture frames.
Only HUD position/size are adapted to this preview; no stock art is synthesized.
"""
import argparse,json,math,struct,sys
from pathlib import Path
import numpy as np
from PIL import Image
from scene_assets import roots,u32,expose_roots

# CharacterKind -> stock texture timeline, including Zelda/Sheik's shared slot.
TEXTURE_FRAMES=dict(zip(['Ca','Dk','Fx','Gw','Kb','Kp','Lk','Lg','Mr','Ms','Mt','Ns','Pe','Pk','Pp','Pr','Ss','Ys','Zd','Fc','Cl','Dr','Fe','Pc','Gn','Sk'],range(26)))

def sample(keys,frame):
    for a,b in zip(keys,keys[1:]):
        if a.frame<=frame<b.frame:
            t=(frame-a.frame)/(b.frame-a.frame)
            if a.interpolation.value=='CONSTANT':return a.value
            if a.interpolation.value=='LINEAR':return a.value+(b.value-a.value)*t
            dt=b.frame-a.frame
            return (2*t**3-3*t*t+1)*a.value+(t**3-2*t*t+t)*dt*(a.slope_out or 0)+(-2*t**3+3*t*t)*b.value+(t**3-t*t)*dt*(b.slope_in or 0)
    return keys[-1].value if frame>=keys[-1].frame else keys[0].value

def run(args):
    sys.path.insert(0,str(args.importer.resolve()))
    from importer.phases.parse.parse import parse_sections
    from importer.phases.describe.helpers.keyframe_decoder import decode_fobjdesc
    from shared.gx_texture import decode_texture
    from render_particles import Bank,render
    data=(args.data/'IfAll.dat').read_bytes();md=32+u32(data,roots(data)['Stc_scemdls'])
    j,a,m=struct.unpack_from('>3I',data,md);a=u32(data,32+a);m=u32(data,32+m)
    specs=[('stock_joint',j,'Joint'),('stock_animjoint',a,'AnimationJoint'),('stock_matanim_joint',m,'MaterialAnimationJoint')]
    sections=parse_sections(expose_roots(data,specs),{n:t for n,_,t in specs},{'filepath':'stock.dat','game':'SMASH_BROS','max_frame':250,'section_names':[]})
    joint,anim,mat=[s.root_node.child for s in sections]
    keys={};f=anim.animation.frame
    while f:keys[f.type]=decode_fobjdesc(f);f=f.next
    if set(keys)!={5,6}:raise ValueError('Unexpected stock motion channels')
    offsets=[[sample(keys[5],i)-sample(keys[5],0),sample(keys[6],i)-sample(keys[6],0)] for i in range(11)]
    ta=mat.animation.texture_animation
    manifest_path=args.output/'manifest.json';manifest=json.loads(manifest_path.read_text())
    sheet=Image.new('RGBA',(8*96,4*96));roster=json.loads(Path(__file__).with_name('roster.json').read_text())
    for n,character in enumerate(roster):
        index=TEXTURE_FRAMES[character['code']];tex=ta.image_table[index];pal=ta.palette_table[index]
        pixels=decode_texture(tex.raw_image_data,tex.width,tex.height,tex.format,pal)
        icon=Image.fromarray(np.array(pixels,dtype=np.uint8).reshape(tex.height,tex.width,4)[::-1].copy()).resize((48,48),Image.Resampling.NEAREST)
        name='stock-'+character['slug'];icon.save(args.output/(name+'.webp'),lossless=True)
        manifest['environment'][name]={'file':name+'.webp','width':48,'height':48,'columns':1,'frames':1,'fps':60,'anchor':[24,24],
            'source':f'IfAll.dat: Stc_scemdls, portrait timeline {index}, original joint channels 5/6', 'lossOffsets':offsets,'lossFrames':10,'pixelsPerGameUnit':20}
        sheet.alpha_composite(icon,((n%8)*96+24,(n//8)*96+16))
    sheet.save(args.data/'stock-portraits.png')
    images=render(Bank(args.data/'EfCoData.dat'),247,32,size=384,units=5)
    atlas=Image.new('RGBA',(384*8,384*4))
    for i,im in enumerate(images):atlas.paste(im,((i%8)*384,(i//8)*384))
    atlas.save(args.output/'stock-loss.webp',lossless=True)
    manifest['environment']['stock-loss']={'file':'stock-loss.webp','width':384,'height':384,'columns':8,'frames':32,'fps':60,'anchor':[192,192],'source':'EfCoData.dat: generator 247 (gfx 0x474), original command stream and texture bank'}
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['data','output','importer']:p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
