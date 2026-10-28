"""Backfill game-derived scales without resampling/re-exporting sprite pixels."""
import argparse,json
from pathlib import Path
from fighter_setup import model_scale,VERSION

def run(data,output):
    path=output/'manifest.json';m=json.loads(path.read_text());audit={}
    codes={s['slug']:s['code'] for s in json.loads(Path(__file__).with_name('roster.json').read_text())};codes['nana']='Nn'
    for key,fighter in m['fighters'].items():
        code=fighter.get('code',codes[key.removesuffix('-left')]);fighter['code']=code;source=data/f'Pl{code}.dat'
        fighter['modelScale']=model_scale(source.read_bytes())
        fighter['modelScaleVersion']=VERSION
        audit[key]={'source':source.name,'commonAttributeOffset':'0x8C','modelScale':fighter['modelScale'],
                    'exportCameraCompensation':fighter.get('scale',1)}
    temp=path.with_suffix('.scale.tmp');temp.write_text(json.dumps(m,indent=2)+'\n');temp.replace(path)
    (output/'fighter-scale-audit.json').write_text(json.dumps(audit,indent=2)+'\n')
    print(f'Applied original game model scales to {len(audit)} fighter facings.')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();run(a.data,a.output)
