"""Backfill posed collision data without rerendering fighter textures."""
import argparse,json,math,sys
from pathlib import Path
from combat_geometry import sample_geometry

def run(args):
    sys.path.insert(0,str(args.importer.resolve()))
    import bpy
    from importer.phases.route.route import route_sections
    from importer.phases.parse.parse import parse_sections
    from importer.phases.describe.describe import describe_scene
    path=args.output/'manifest.json';m=json.loads(path.read_text())
    codes={f['slug']:f['code'] for f in json.loads(Path(__file__).with_name('roster.json').read_text())}
    for key,f in m['fighters'].items():
        code=f.get('code') or codes[key.removesuffix('-left')]
        options={'game':'SMASH_BROS','filepath':f'Pl{code}Nr.dat','section_names':[],'max_frame':600}
        data=(args.data/f'Pl{code}Nr.dat').read_bytes()
        model=describe_scene(parse_sections(data,route_sections(data,game='SMASH_BROS'),options),options).models[0]
        scene=args.data/'rendered'/f'{key}.blend'
        if not scene.exists() and key=='roy-left':scene=args.data/'rendered'/'roy.blend'
        bpy.ops.wm.open_mainfile(filepath=str(scene))
        sources={f['clips'][c]['source'] for c in ['idle','smash']}
        if not sources.issubset(bpy.data.actions.keys()):bpy.ops.wm.open_mainfile(filepath=str(scene)+'1')
        arm=next(o for o in bpy.context.scene.objects if o.type=='ARMATURE')
        arm.rotation_euler.z=math.pi/2 if f['facing']=='right' else -math.pi/2
        f['combatGeometry']=sample_geometry(bpy.context.scene,arm,model,f,(args.data/f'Pl{code}.dat').read_bytes(),(args.data/'PlCo.dat').read_bytes())
        print(key,'reach',f['combatGeometry']['maxReach'],flush=True)
    tmp=path.with_suffix('.geometry.tmp');tmp.write_text(json.dumps(m,indent=2)+'\n');tmp.replace(path)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['importer','data','output']:p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
