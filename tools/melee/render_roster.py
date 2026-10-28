"""Render both actual camera facings of the roster into isolated staging folders.

Resume skips complete exports. Failure stays in status.json; it never causes
another fighter's art to be substituted. Install with import_roster.py only
after checking its asset errors and remaining fidelity review items.
"""
import argparse,concurrent.futures,json,subprocess,sys
from pathlib import Path
from fighter_materials import MATERIAL_VERSION

def run(args):
    args.output.mkdir(parents=True,exist_ok=True)
    roster=json.loads(Path(__file__).with_name('roster.json').read_text())+[{'code':'Nn','slug':'nana'}]
    def render(character):
        code=character['code'];dest=args.output/code;dest.mkdir(exist_ok=True)
        with (args.output/(code+'.log')).open('a') as log:
            for facing in ['right','left']:
                key=character['slug']+('-left' if facing=='left' else '')
                if args.resume and (dest/'manifest.json').exists():
                    fighter=json.loads((dest/'manifest.json').read_text())['fighters'].get(key)
                    if fighter and fighter.get('materialVersion')==MATERIAL_VERSION and fighter.get('combatGeometry',{}).get('version')=='posed-hitboxes-v1' and len(fighter['clips'])==7 and not any(c.get('clippedFrames') for c in fighter['clips'].values()):continue
                command=[sys.executable,str(Path(__file__).with_name('render_preview.py')),'--importer',str(args.importer),'--data',str(args.data),'--output',str(dest),'--fighter',code,'--facing',facing]
                result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
                if result.returncode:return {'code':code,'status':'failed','facing':facing,'exit':result.returncode}
        return {'code':code,'status':'rendered; review required'}
    results=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(render,c) for c in roster]):
            results.append(future.result());(args.output/'status.json').write_text(json.dumps(results,indent=2)+'\n');print(results[-1],flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['importer','data','output']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--workers',type=int,choices=range(1,5),default=2);p.add_argument('--resume',action='store_true');run(p.parse_args())
