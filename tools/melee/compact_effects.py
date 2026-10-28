"""Losslessly repack visible KO pixels; retain source frame coordinates.

Black screen-blended texels have no contribution. Convert them to transparent
without changing their premultiplied RGB, then shelf-pack the nonempty bounds.
Run after render_match_effects.py / render_particles.py.
"""
import argparse,json,math
from pathlib import Path
import numpy as np
from PIL import Image


def screen_alpha(image):
    pixels=np.array(image).astype(float)
    rgb=pixels[:,:,:3]*pixels[:,:,3:4]/255
    alpha=rgb.max(axis=2)
    color=np.divide(rgb*255,alpha[:,:,None],out=np.zeros_like(rgb),where=alpha[:,:,None]>0)
    return Image.fromarray(np.dstack([np.rint(color),np.rint(alpha)]).clip(0,255).astype('uint8'))


def compact(output):
    path=output/'manifest.json';m=json.loads(path.read_text())
    for name in ['ko-p1','ko-p2','ko-particles','normal-impact']:
        if name not in m['environment']:continue
        c=m['environment'][name]
        if c.get('rects'):continue
        atlas=Image.open(output/c['file']).convert('RGBA');tiles=[];rects=[]
        x=y=row=0;width=2048
        for i in range(c['frames']):
            sx=i%c['columns']*c['width'];sy=i//c['columns']*c['height']
            im=atlas.crop((sx,sy,sx+c['width'],sy+c['height']))
            if name in ['ko-p1','ko-p2']:im=screen_alpha(im)
            b=im.getchannel('A').getbbox()
            if not b:rects.append([0,0,0,0,0,0]);continue
            im=im.crop(b);w,h=im.size
            if x+w+2>width:x=0;y+=row+2;row=0
            rects.append([x,y,w,h,b[0],b[1]]);tiles.append((im,(x,y)))
            x+=w+2;row=max(row,h)
        packed=Image.new('RGBA',(width,y+row))
        for im,xy in tiles:packed.paste(im,xy)
        c['file']=Path(c['file']).stem+'-compact.webp';c['rects']=rects;c['decodedSize']=list(packed.size)
        packed.save(output/c['file'],lossless=True,method=6)
        print(name,atlas.size,'->',packed.size,round(packed.width*packed.height*4/1024**2,2),'MiB')
    # The uncolored intermediate model is not used by playback.
    m['environment'].pop('ko',None)
    path.write_text(json.dumps(m,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);compact(p.parse_args().output)
