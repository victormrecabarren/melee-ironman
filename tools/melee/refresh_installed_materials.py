"""Bounded parallel material refresh; only the parent publishes the manifest."""
import argparse,concurrent.futures,json,shutil,subprocess,sys
from pathlib import Path
from fighter_materials import MATERIAL_VERSION

def run(args):
    path=args.output/'manifest.json';initial=json.loads(path.read_text());groups={}
    for key,fighter in initial['fighters'].items():
        if fighter.get('materialVersion')==MATERIAL_VERSION:continue
        signature=tuple(sorted(c['file'] for c in fighter['clips'].values()))
        groups.setdefault(signature,[]).append(key)
    ordered=sorted(groups.values(),key=lambda ks:(not ks[0].startswith('donkey-kong'),ks[0]))
    args.staging.mkdir(exist_ok=True,parents=True)
    def render(keys):
        key=keys[0];folder=args.staging/key;folder.mkdir(exist_ok=True)
        (folder/'manifest.json').write_text(json.dumps(initial))
        command=[sys.executable,str(Path(__file__).with_name('rerender_materials.py')),
          '--importer',str(args.importer),'--data',str(args.data),'--output',str(folder),
          '--staging',str(folder/'work'),'--baseline',str(args.output),'--device','CPU','--keys',key]
        with (folder/'render.log').open('w') as log:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
        if result.returncode:return keys,{'error':result.returncode}
        return keys,json.loads((folder/'manifest.json').read_text())['fighters'][key]
    report={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        for future in concurrent.futures.as_completed([pool.submit(render,keys) for keys in ordered]):
            keys,fighter=future.result();key=keys[0]
            if 'error' in fighter:
                report[key]=fighter;print('FAILED',key,fighter,flush=True)
            else:
                for c in fighter['clips'].values():shutil.copy2(args.staging/key/c['file'],args.output/c['file'])
                current=json.loads(path.read_text())
                for alias in keys:
                    target=current['fighters'][alias]
                    target['materialVersion']=MATERIAL_VERSION;target['materialAudit']=fighter['materialAudit']
                    for kind,clip in fighter['clips'].items():target['clips'][kind]['file']=clip['file']
                temp=path.with_suffix('.materials.tmp');temp.write_text(json.dumps(current,indent=2)+'\n');temp.replace(path)
                report[key]={'published':keys,'frames':sum(c['frames'] for c in fighter['clips'].values())}
                print('PUBLISHED',key,report[key],flush=True)
            (args.staging/'status.json').write_text(json.dumps(report,indent=2)+'\n')
    if any('error' in r for r in report.values()):raise SystemExit('Some fighters failed; inspect staging logs')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['importer','data','output','staging']:p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--workers',type=int,choices=[1,2,3,4],default=3);run(p.parse_args())
