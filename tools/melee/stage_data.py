"""Extract Final Destination camera/blast markers and tracking parameters."""
import argparse
import json
import struct
from pathlib import Path
from dat_assets import roots
from move_data import u32


def read_stage(directory):
    data = (directory/'GrNLa.dat').read_bytes()
    symbols = roots(data)
    head = symbols['map_head']
    entry = 32+u32(data, head)
    joint, pairs, count = struct.unpack_from('>3I', data, entry)
    joints = []
    def visit(pointer, parent=(0, 0, 0)):
        if not pointer: return
        p = 32+pointer
        rotation = struct.unpack_from('>3f', data, p+20)
        scale = struct.unpack_from('>3f', data, p+32)
        if rotation != (0., 0., 0.) or scale != (1., 1., 1.):
            raise ValueError('Stage marker transform needs full matrix support')
        position = tuple(a+b for a,b in zip(parent, struct.unpack_from('>3f', data, p+44)))
        joints.append(position)
        visit(u32(data, p+8), position)
        visit(u32(data, p+12), parent)
    visit(joint)
    markers = {marker: joints[index] for index,marker in
               [struct.unpack_from('>2h', data, 32+pairs+i*4) for i in range(count)]}
    def bounds(a, b):
        a,b = markers[a],markers[b]
        return dict(left=min(a[0],b[0]), right=max(a[0],b[0]), bottom=min(a[1],b[1]), top=max(a[1],b[1]))
    p = symbols['grGroundParam']
    return {'source':'GrNLa.dat: map_head joint markers 0x94–0x98 and grGroundParam',
            'cameraOrigin':list(markers[0x94]), 'cameraBounds':bounds(0x95,0x96),
            'blastBounds':bounds(0x97,0x98),
            'tracking':{'ratio':struct.unpack_from('>f',data,p+0x20)[0],
                        'smooth':struct.unpack_from('>f',data,p+0x28)[0]},
            'projection':{'gameUnitMeters':.1,'fighterOrthoWidth':4.8,'stageOrthoWidth':21}}


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=p.parse_args();path=args.output/'manifest.json';m=json.loads(path.read_text())
    m['stageInfo']=read_stage(args.data);path.write_text(json.dumps(m,indent=2)+'\n')
