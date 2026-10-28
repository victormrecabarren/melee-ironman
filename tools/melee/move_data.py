"""Decode bounded fighter command streams and sword/voice parameters.

Bounded loops, jumps and subroutines execute with explicit stack/instruction
limits so malformed or unsupported streams cannot silently lose events.
Schema layout is documented by HSDLib; timing matches lbcommand.c.
"""
import argparse
import json
import struct
from pathlib import Path
from dat_assets import roots

SCHEMA = json.loads(Path(__file__).with_name('command_schema.json').read_text())['commands']


def u32(data, offset):
    if not 0 <= offset <= len(data)-4:
        raise ValueError('Pointer outside DAT')
    return struct.unpack_from('>I', data, offset)[0]


def decode_script(data, offset):
    frame = 0
    events = []
    loops, calls = [], []
    for _ in range(8192):
        if offset < 32 or offset+4 > len(data):
            raise ValueError('Command pointer outside DAT')
        opcode = data[offset] >> 2
        desc = SCHEMA[str(opcode)]
        bits = max(32, 6 + sum(f[1] for f in desc['fields']))
        chunk = data[offset:offset+bits//8]
        if len(chunk) != bits//8:
            raise ValueError('Truncated command')
        value, remaining, fields = int.from_bytes(chunk, 'big'), bits-6, {}
        for name, width, signed in desc['fields']:
            remaining -= width
            v = (value >> remaining) & ((1 << width)-1)
            if signed and v & (1 << (width-1)):
                v -= 1 << width
            fields[name] = v
        following = offset+bits//8
        if opcode == 3:
            if not 1 <= fields['Count'] <= 256 or len(loops) >= 16:
                raise ValueError('Unbounded loop')
            loops.append([following, fields['Count']])
        elif opcode == 4:
            if not loops: raise ValueError('Loop end without start')
            loops[-1][1] -= 1
            if loops[-1][1]: following=loops[-1][0]
            else: loops.pop()
        elif opcode in (5,7):
            if opcode == 5:
                if len(calls) >= 16: raise ValueError('Subroutine recursion limit')
                calls.append(following)
            following=32+fields['Pointer']
        elif opcode == 6:
            if not calls: raise ValueError('Return without subroutine')
            following=calls.pop()
        elif opcode == 8:
            raise ValueError('Animation timer reset requires explicit support')
        if opcode == 1:
            frame += fields['Frame']
        elif opcode == 2:
            frame = max(frame, fields['Frame'])
        elif opcode not in (3,4,5,6,7):
            events.append({'frame': frame, 'opcode': opcode, 'name': desc['name'], 'fields': fields})
        if opcode == 0:
            return events
        offset = following
    raise ValueError('Command stream did not terminate')


def read_move(path, action):
    data = Path(path).read_bytes()
    root = next(iter(roots(data).values()))
    table = 32 + u32(data, root+12)
    found = None
    # Entries are 24 bytes; selected moves are in the common 341-motion table.
    for index in range(341):
        entry = table + index*24
        p = 32 + u32(data, entry)
        if not 32 <= p < len(data):
            continue
        end = data.find(b'\0', p, min(len(data), p+256))
        if end < 0:
            continue
        name = data[p:end].decode('ascii', errors='replace')
        if name.endswith('_ACTION_'+action+'_figatree'):
            candidate = (index, 32 + u32(data, entry+12))
            # Peach's common slot is a dispatcher; her three weapon scripts
            # share this animation. Select the first actual weapon (club).
            if any(e['opcode'] == 11 for e in decode_script(data,candidate[1])):
                found = candidate
                break
    if not found:
        raise ValueError(f'Missing action {action}')
    events = decode_script(data, found[1])
    hits = [e for e in events if e['opcode'] == 11]
    if not hits:
        raise ValueError(f'{action} creates hitboxes in fighter code, not its command stream')
    clear = max((e['frame'] for e in events if e['opcode'] == 16), default=hits[-1]['frame']+1)
    result = {'action': action, 'actionIndex': found[0], 'source': Path(path).name,
              'fps': 60, 'activeStart': hits[0]['frame'], 'activeEnd': clear,
              'events': events, 'hitboxes': [h['fields'] for h in hits]}
    # Keep all actual hitbox types, including Roy's weak normal tip.
    result['selectedHitbox'] = hits[0]['fields']['ID']
    phases=[]
    active=False
    for event in events:
        if event['opcode']==16: active=False
        elif event['opcode']==11 and not active:
            phases.append({'frame':event['frame'],'hitbox':event['fields']})
            active=True
    result['hitPhases']=phases
    charge = next((e for e in events if e['opcode']==56), None)
    if charge:
        result['charge']={'frame':charge['frame'], 'frames':charge['fields']['Charge Frames'],
            'damageMultiplier':charge['fields']['Charge Rate']/256,
            'colorAnimation':charge['fields']['Color Animation']}
    sfx = 32 + u32(data, root+0x4c)
    smash = 32 + u32(data, sfx)
    count, sounds = struct.unpack_from('>II', data, smash)
    if count > 64:
        raise ValueError('Invalid smash voice count')
    result['voices'] = [u32(data, 32+sounds+i*4) for i in range(count)]
    sword_offsets = {'PlMs':0x78, 'PlFe':0x78, 'PlLk':0x64, 'PlCl':0x64}
    if Path(path).stem in sword_offsets and any(e['opcode'] == 49 for e in events):
        p = 32 + u32(data, root+4) + sword_offsets[Path(path).stem]
        inner, outer = struct.unpack_from('>2f', data, p)
        bone, bottom, top = struct.unpack_from('>Iff', data, p+20)
        result['trail'] = {'innerShrink': inner, 'outerShrink': outer,
            'alphaStart': data[p+8], 'alphaEnd': data[p+9],
            'innerColor': list(data[p+10:p+13]), 'outerColor': list(data[p+14:p+17]),
            'bone': bone, 'bottom': bottom, 'top': top,
            'start': next(e['frame'] for e in events if e['opcode'] == 49 and e['fields']['Render Status'] == 0),
            'end': next(e['frame'] for e in events if e['opcode'] == 49 and e['fields']['Render Status'] == 255)}
    return result


def read_action(path, action):
    """Non-attacking actions have scripts too; do not require a hitbox."""
    data=Path(path).read_bytes();root=next(iter(roots(data).values()))
    table=32+u32(data,root+12)
    for index in range(341):
        entry=table+index*24;p=32+u32(data,entry)
        if not 32<=p<len(data):continue
        end=data.find(b'\0',p,min(len(data),p+256))
        if data[p:end].endswith(('_ACTION_'+action+'_figatree').encode()):
            return {'action':action,'actionIndex':index,'source':Path(path).name,
                    'events':decode_script(data,32+u32(data,entry+12))}
    raise ValueError(f'Missing action {action}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    path = args.output/'manifest.json'
    manifest = json.loads(path.read_text())
    for code, slug, action in [('Fe','roy','AttackS4'),('Dr','dr-mario','AttackS4S')]:
        move = read_move(args.data/f'Pl{code}.dat', action)
        manifest['fighters'][slug]['move'] = move
        print(slug, 'active frames', move['activeStart'], 'to', move['activeEnd']-1)
    path.write_text(json.dumps(manifest, indent=2)+'\n')
