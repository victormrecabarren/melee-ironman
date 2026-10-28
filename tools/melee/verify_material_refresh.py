"""Check that a material-only rerender preserves source animation silhouettes."""
import argparse,json
from pathlib import Path
import numpy as np
from PIL import Image
from fighter_materials import MATERIAL_VERSION

def verify(output,keys=None):
    manifest=json.loads((output/'manifest.json').read_text());report={}
    for key,fighter in manifest['fighters'].items():
        if keys and key not in keys:continue
        if fighter.get('materialVersion')!=MATERIAL_VERSION:continue
        clips={}
        for name,clip in fighter['clips'].items():
            old=clip['file'].replace('-materials-v1.webp','.webp')
            before=Image.open(output/old);after=Image.open(output/clip['file'])
            if before.size!=after.size:raise ValueError(f'{key}/{name}: atlas shape changed')
            worst=1.;max_center=0.
            for i in range(clip['frames']):
                x=i%8*512;y=i//8*384;b=(x,y,x+512,y+384)
                a=np.array(before.crop(b).getchannel('A'))>128;c=np.array(after.crop(b).getchannel('A'))>128
                union=(a|c).sum();iou=(a&c).sum()/union if union else 0
                worst=min(worst,float(iou))
                ab=np.argwhere(a);cb=np.argwhere(c)
                if not len(ab) or not len(cb):raise ValueError(f'{key}/{name}/{i}: blank')
                max_center=max(max_center,float(np.linalg.norm(ab.mean(axis=0)-cb.mean(axis=0))))
            clips[name]={'minSilhouetteIoU':round(worst,5),'maxCentroidShiftPx':round(max_center,3)}
        report[key]=clips
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--keys',nargs='+');p.add_argument('--report',type=Path)
    args=p.parse_args();result=verify(args.output,args.keys)
    if args.report:args.report.write_text(json.dumps(result,indent=2)+'\n')
    for key,clips in result.items():print(key,'worst IoU',min(c['minSilhouetteIoU'] for c in clips.values()),'max shift',max(c['maxCentroidShiftPx'] for c in clips.values()))
