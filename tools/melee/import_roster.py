"""Validate staged fighter atlases and install complete exports into the preview.

Atlas integrity is a mechanical check, not a claim of full engine fidelity.
The report retains unsupported commands and effect IDs for review.
"""
import argparse,json,shutil
from pathlib import Path
from PIL import Image
from accessory_dynamics import VERSION as DYNAMICS_VERSION, SUPPORTED as DYNAMIC_CODES
from fighter_setup import VERSION as SCALE_VERSION
from fighter_materials import MATERIAL_VERSION
from combat_geometry import VERSION as GEOMETRY_VERSION
REQUIRED={'idle','fall','landing','smash','hit','recoil','tumble'}

def inspect(fighter,folder):
    problems=[]
    if fighter.get('modelScaleVersion')!=SCALE_VERSION or not .1<=fighter.get('modelScale',0)<=4:problems.append('Missing original runtime model scale')
    if fighter.get('code')=='Gw' and fighter.get('specialSetup',{}).get('version')!='disc-gamewatch-setup-v1':problems.append('Missing Game & Watch runtime setup')
    if fighter.get('combatGeometry',{}).get('version')!=GEOMETRY_VERSION:problems.append('Missing posed combat geometry; run export_combat_geometry.py')
    if fighter.get('materialVersion')!=MATERIAL_VERSION:problems.append('Stale material conversion; rerender with the source specular policy')
    if not REQUIRED<=set(fighter['clips']) or set(fighter['clips'])-REQUIRED-{'taunt'}:problems.append('Missing or unsupported motion clips')
    if fighter.get('code') in DYNAMIC_CODES:
        dynamics=fighter.get('accessoryDynamics',{})
        if dynamics.get('version')!=DYNAMICS_VERSION or any(c['source'] not in dynamics.get('clips',{}) for c in fighter['clips'].values()):
            problems.append('Missing source accessory dynamics for one or more clips')
    bounds=[]
    for kind,clip in fighter['clips'].items():
        if kind in ('hit','recoil') and (len(clip.get('damageAnchors',[]))!=clip['frames'] or len(clip.get('frameCenters',[]))!=clip['frames']):
            problems.append(f'{kind}: missing damage metadata; run backfill_damage_metadata.py')
        if clip.get('clippedFrames'):problems.append(f"{kind}: clipped frames {clip['clippedFrames']}")
        image=Image.open(folder/clip['file']);expected=(4096,384*((clip['frames']+7)//8))
        if image.size!=expected:problems.append(f'{kind}: invalid atlas size')
        boxes=[]
        for frame in range(clip['frames']):
            x,y=frame%8*512,frame//8*384
            box=image.crop((x,y,x+512,y+384)).getchannel('A').point(lambda a:255 if a>10 else 0).getbbox()
            if box:boxes.append(box)
            else:problems.append(f'{kind}: blank frame {frame}')
        if boxes:
            clip['bounds']=[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
            if kind in ['idle','fall','landing']:bounds+=boxes
    if bounds:fighter['readyBounds']=[min(b[0] for b in bounds),min(b[1] for b in bounds),max(b[2] for b in bounds),max(b[3] for b in bounds)]
    return problems

def run(args):
    path=args.output/'manifest.json';manifest=json.loads(path.read_text());report=dict(manifest.get('rosterAudit',{}))
    for file in sorted(args.staged.glob('*/manifest.json')):
        data=json.loads(file.read_text())
        for key,fighter in data['fighters'].items():
            if args.only and key not in args.only:continue
            problems=inspect(fighter,file.parent)
            report[key]={'assetErrors':problems,'gfx':sorted(set(e['fields']['GFX ID'] for e in fighter['move']['events'] if e['opcode']==10)),
                'needsReview':sorted(set(e['opcode'] for e in fighter['move']['events'])&{19,35,40,41,49}),
                'status':'rejected' if problems else 'rendered; fidelity review separate',
                'unrenderedGfx':sorted({e['fields']['GFX ID'] for e in fighter['move']['events'] if e['opcode']==10}-set(map(int,manifest.get('effectMap',{})))-{1299}),
                'unrenderedImpactElements':sorted({h['Element'] for h in fighter['move']['hitboxes'] if ({0:'normal-impact',1:'fire-impact',2:'electric',3:'slash',13:'dark-impact'}.get(h['Element'])) not in manifest['environment']})}
            if problems:continue
            if key in ['dr-mario','roy'] and not args.replace_baseline:
                report[key]['status']='existing reviewed baseline preserved'
                continue
            for clip in fighter['clips'].values():shutil.copy2(file.parent/clip['file'],args.output/clip['file'])
            manifest['fighters'][key]=fighter
    manifest['rosterAudit']=report
    path.write_text(json.dumps(manifest,indent=2)+'\n')
    (args.output/'roster-audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v['assetErrors'] or 'installed' for k,v in report.items()},indent=2))
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['staged','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--only',nargs='+');p.add_argument('--replace-baseline',action='store_true');run(p.parse_args())
