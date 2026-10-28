"""Losslessly trim fighter frames into GPU-sized pages; preserve logical anchors.

No resampling, frame removal, or timing changes. Unchanged frame pixels may share
one packed rectangle. Original atlases are retained for reproducibility.
"""
import argparse,hashlib,json
from pathlib import Path
from PIL import Image
PAGE=2048
VERSION='trimmed-pages-v1'

def compact_clip(folder,clip,width=512,height=384,columns=8,screen=False):
    if clip.get('packing')==VERSION:return clip
    original=Image.open(folder/clip['file']).convert('RGBA')
    pages=[];rects=[];seen={};page=Image.new('RGBA',(PAGE,PAGE));x=y=row=0
    stem=Path(clip['file']).stem+'-packed-v1'
    def publish():
        filename=f'{stem}-{len(pages)}.webp'
        packed=page.crop((0,0,PAGE,max(1,y+row+1)))
        packed.save(folder/filename,lossless=True,method=4)
        pages.append({'file':filename,'width':packed.width,'height':packed.height})
    for frame in range(clip['frames']):
        sx=frame%columns*width;sy=frame//columns*height
        tile=original.crop((sx,sy,sx+width,sy+height))
        if screen:
            from compact_effects import screen_alpha
            tile=screen_alpha(tile)
        box=tile.getchannel('A').getbbox()
        if not box:rects.append([0,0,0,0,0,0,0]);continue
        tile=tile.crop(box);w,h=tile.size
        key=(w,h,hashlib.sha256(tile.tobytes()).digest())
        if key not in seen:
            if x+w+2>PAGE:x=0;y+=row+2;row=0
            if y+h+2>PAGE:
                publish();page=Image.new('RGBA',(PAGE,PAGE));x=y=row=0
            page.paste(tile,(x,y));seen[key]=[len(pages),x,y,w,h]
            x+=w+2;row=max(row,h)
        rects.append([*seen[key],box[0],box[1]])
    publish()
    result={**clip,'sourceAtlas':clip['file'],'file':pages[0]['file'],'pages':pages,'rects':rects,'packing':VERSION}
    result['decodedBytes']=sum(p['width']*p['height']*4 for p in pages)
    return result

def run(output,only=None,environment=False):
    path=output/'manifest.json';m=json.loads(path.read_text());report={}
    for key,fighter in ([] if environment else m['fighters'].items()):
        if only and key not in only:continue
        before=after=0
        for name,clip in fighter['clips'].items():
            if clip.get('packing')==VERSION:continue
            before+=Image.open(output/clip['file']).width*Image.open(output/clip['file']).height*4
            packed=compact_clip(output,clip,m['width'],m['height'],m['columns'])
            fighter['clips'][name]=packed;after+=packed['decodedBytes']
        if before:
            report[key]={'beforeMiB':round(before/2**20,2),'afterMiB':round(after/2**20,2)}
            print(key,report[key],flush=True)
    if environment:
        for name,clip in m['environment'].items():
            if clip.get('rects'):continue # already compacted, either format
            original=Image.open(output/clip['file'])
            packed=compact_clip(output,clip,clip['width'],clip['height'],clip['columns'],
                screen=name.endswith('dust') or name in ['smash-ground','slash','arrival-glow'])
            m['environment'][name]=packed
            report[name]={'beforeMiB':round(original.width*original.height*4/2**20,2),'afterMiB':round(packed['decodedBytes']/2**20,2)}
            print(name,report[name],flush=True)
    tmp=path.with_suffix('.packing.tmp');tmp.write_text(json.dumps(m,indent=2)+'\n');tmp.replace(path)
    (output/('environment-packing-report.json' if environment else 'fighter-packing-report.json')).write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--only',nargs='+');p.add_argument('--environment',action='store_true');a=p.parse_args();run(a.output,a.only,a.environment)
