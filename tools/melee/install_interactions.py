"""Publish validated taunts and original smash-charge commands as one manifest.

Only the new taunt clip is copied; reviewed combat clips and geometry remain
unchanged. All sprite pages are present before the manifest is atomically moved.
"""
import argparse,json,shutil
from pathlib import Path
from import_roster import inspect
from compact_fighters import compact_clip
from common_states import color_cycle
from dat_assets import roots
from move_data import u32

def run(staged,output,data):
    path=output/'manifest.json';manifest=json.loads(path.read_text());checked={}
    common=(data/'PlCo.dat').read_bytes();table=32+u32(common,roots(common)['ftLoadCommonData']+0x18)
    for key,current in manifest['fighters'].items():
        folder=staged/key;source=json.loads((folder/'manifest.json').read_text())['fighters'][key]
        problems=inspect(source,folder)
        if 'taunt' not in source['clips']:problems.append('Missing taunt')
        if problems:raise ValueError(f'{key}: {problems}')
        checked[key]=(folder,source)
    for key,(folder,source) in checked.items():
        current=manifest['fighters'][key]
        clip=compact_clip(folder,source['clips']['taunt'])
        clip.update(anchor=source['anchor'],exportScale=source['scale'])
        for filename in [clip['sourceAtlas'],*[p['file'] for p in clip['pages']]]:shutil.copy2(folder/filename,output/filename)
        current['clips']['taunt']=clip;current['taunt']=source['taunt']
        current['taunt']['overlays']={str(e['fields']['ID']):color_cycle(common,table,e['fields']['ID'],max(1,e['fields']['Duration']))
            for e in current['taunt']['events'] if e['name']=='Color Animation'}
        charge=next(e for e in current['move']['events'] if e['opcode']==56);f=charge['fields']
        current['move']['charge']={'frame':charge['frame'],'frames':f['Charge Frames'],'damageMultiplier':f['Charge Rate']/256,'colorAnimation':f['Color Animation']}
    manifest['effectMap'].update({'1022':'charge-dust','1024':'taunt-step-dust','1025':'taunt-step-dust','1052':'taunt-sparkle','1015':'taunt-puff-dust','1030':'taunt-ring-dust'})
    for kind in ['taunt-puff-dust','taunt-ring-dust']:
        manifest['environment'][kind]['pixelsPerGameUnit']=512/12*.1
    for kind in ['charge-dust','taunt-step-dust','taunt-sparkle','taunt-puff-dust','taunt-ring-dust']:
        c=manifest['environment'][kind]
        manifest['environment'][kind]=compact_clip(output,c,c['width'],c['height'],c['columns'],screen=kind.endswith('dust'))
    manifest['interactionSource']={'charge':'Pl*.dat opcode 56 / PlCo color119 and shake table / ft_0DF0.c',
        'taunt':'Pl*AJ.dat Appeal/AppealL/AppealR; Pl*.dat command streams; embedded Dr/Cl item actions',
        'count':len(checked),'scaleCorrection':'HSD_JObjMakeMatrix retains classical joint scale in its SRT matrix'}
    temp=path.with_suffix('.interactions.tmp');temp.write_text(json.dumps(manifest,indent=2)+'\n');temp.replace(path)
    print(f'Installed {len(checked)} validated taunts and charge configurations',flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['staged','output','data']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.staged,a.output,a.data)
