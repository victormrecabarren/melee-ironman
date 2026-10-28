"""Read revival overlays and normal landing commands from the supplied disc.

Color command execution follows doldecomp/melee lb_013B.c and lbcommand.c.
Only commands actually present in these two scripts are supported; others fail.
"""
import argparse
import json
import struct
from pathlib import Path
from dat_assets import roots
from move_data import u32, decode_script


def color_cycle(data, table, index, frames):
    start = 32 + u32(data, table + index * 8)
    pc, wait, enabled = start, 0, False
    stack = []
    finished = False
    effects = []
    rgba, delta, result = [0.] * 4, [0.] * 4, []
    light,light_delta,light_frames=[0.]*4,[0.]*4,[]
    for frame in range(frames):
        wait = max(0, wait - 1)
        for _ in range(128):
            if wait or finished:
                break
            word = u32(data, pc); op, value = word >> 26, word & 0x3ffffff
            pc += 4
            if op == 0 or op == 10:
                finished = True
            elif op == 3:
                stack.append(['loop', pc, value])
            elif op == 4:
                if not stack or stack[-1][0] != 'loop': raise ValueError('Invalid color loop')
                stack[-1][2] -= 1
                if stack[-1][2]: pc = stack[-1][1]
                else: stack.pop()
            elif op == 5:
                stack.append(['call', pc+4]); pc = 32 + u32(data, pc)
            elif op == 6:
                if not stack or stack[-1][0] != 'call': raise ValueError('Invalid color return')
                pc = stack.pop()[1]
            elif op == 7:
                pc = 32 + u32(data, pc)
            elif op == 11:
                wait += value
            elif op == 12:
                enabled = False
            elif op in (13,14):
                light=list(data[pc:pc+4]);light_delta=[0.]*4;pc+=4
            elif op == 15:
                if not value:raise ValueError('Zero light interpolation duration')
                light_delta=[(v+.5-int(light[i]))/value for i,v in enumerate(data[pc:pc+4])];pc+=4
            elif op == 17:
                light=[0.]*4;light_delta=[0.]*4
            elif op == 16:
                # Light direction alone does not enable the light channel.
                pass
            elif op == 18:
                enabled = True; rgba = list(data[pc:pc+4]); delta = [0.] * 4; pc += 4
            elif op == 19:
                if not value: raise ValueError('Zero color interpolation duration')
                delta = [(v + .5 - int(rgba[i])) / value for i, v in enumerate(data[pc:pc+4])]; pc += 4
            elif op in (21, 22):
                # Fighter callbacks: graphics (20 bytes) / sound (12 bytes).
                # This export executes the color channel only; effects/audio
                # are rendered separately, never mistaken for color opcodes.
                if op == 21:
                    effects.append({'frame':frame, 'bone':(word >> 18) & 255,
                                    'gfx':u32(data,pc) >> 16})
                pc += 16 if op == 21 else 8
            else:
                raise ValueError(f'Unsupported color opcode {op} at {pc-4:#x}')
        else:
            raise ValueError('Color script failed to wait')
        if enabled and not finished:
            rgba = [v + d for v, d in zip(rgba, delta)]
        light=[v+d for v,d in zip(light,light_delta)];light_frames.append([int(v)&255 for v in light])
        result.append([int(v) & 255 for v in rgba] if enabled and not finished else [0, 0, 0, 0])
    return {'source': f'PlCo.dat: color animation {index}', 'fps': 60, 'rgba': result, 'effects':effects,'lightRgba':light_frames}


def read_common(directory):
    data = (directory / 'PlCo.dat').read_bytes(); root = roots(data)['ftLoadCommonData']
    common, table = 32 + u32(data, root), 32 + u32(data, root + 0x18)
    result = {'source': 'GALE01 revision 2', 'postDropFrames': u32(data, common + 0x5d8),
        'hitlag': dict(zip(['maximum','damageMultiplier','base'],struct.unpack_from('>3f',data,common+0x194))),
        'platformOverlay': color_cycle(data, table, 10, 56),
        'postDropOverlay': color_cycle(data, table, 9, 11), 'landing': {},
        # ftCo_Damage: electric uses color index 15 + knockback level;
        # level 3 is the launched/tumbling reaction used by this KO demo.
        'normalDamageOverlay': color_cycle(data, table, 4, 65),
        'electricDamageOverlay': color_cycle(data, table, 18, 65),
        'fireDamageOverlay': color_cycle(data, table, 14, 65),
        'darkDamageOverlay': color_cycle(data, table, 38, 65),
        'koScale':struct.unpack_from('>f',data,common+0x4f4)[0],
        'koColors': [[list(data[32+u32(data,root+offset)+port*4:32+u32(data,root+offset)+port*4+4])
                      for offset in [0x48,0x4c]] for port in range(4)]}
    for code, slug in [('Dr','dr-mario'), ('Fe','roy')]:
        fighter = (directory / f'Pl{code}.dat').read_bytes(); r = next(iter(roots(fighter).values()))
        # ftCo_SM_Landing = 35; state 42 references this submotion.
        entry = 32 + u32(fighter, r+12) + 35*24
        commands = decode_script(fighter, 32+u32(fighter, entry+12))
        effect = next(e for e in commands if e['opcode'] == 55)
        result['landing'][slug] = {'source': f'Pl{code}.dat: submotion 35', **effect}
        if effect['fields']['Graphic ID'] != 1028:
            raise ValueError('Landing effect mapping needs review')
    result['hitlag']['electricMultiplier'] = struct.unpack_from('>f',data,common+0x1a4)[0]
    # ftCo_80090594 / ftCo_80090690: render-only damage shifts, independent
    # of the held skeleton pose, knockback position, and controller-driven SDI.
    shifts = 32 + u32(data, root + 0x24)
    result['damageModelShift'] = {
        'source': 'PlCo.dat: ftLoadCommonData.x24; common offsets 0x168/0x16C',
        'fps': 60,
        'durationMultiplier': struct.unpack_from('>f', data, common+0x168)[0],
        'durationBase': struct.unpack_from('>f', data, common+0x16c)[0],
        'tables': {}
    }
    for index, name in enumerate(['air', 'ground', 'electric']):
        pointer, count = struct.unpack_from('>2I', data, shifts+index*8)
        if not 0 < count <= 256: raise ValueError('Invalid damage-shift table')
        result['damageModelShift']['tables'][name] = [
            list(struct.unpack_from('>2f', data, 32+pointer+frame*8)) for frame in range(count)]
    shake=32+u32(data,root+0x2c)
    pointer,count=struct.unpack_from('>2I',data,shake)
    result['smashCharge']={'source':'PlCo.dat x2C / ft_0DF0.c; color animation 119',
        'fps':60,'shake':[list(struct.unpack_from('>2f',data,32+pointer+i*8)) for i in range(count)],
        'soundDelayFrames':struct.unpack_from('>f',data,common+0x7c8)[0], 'soundId':123,
        'overlay':color_cycle(data,table,119,60)}
    result['arrival']={'source':'ft_0C31.c EntryStart: color 117, GFX 0x43E (EfCoData model 36)',
        'startFrames':u32(data,common+0x6bc),'endFrames':u32(data,common+0x6c0),
        'overlay':color_cycle(data,table,117,60)}
    return result


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);args=p.parse_args()
    path=args.output/'manifest.json'; manifest=json.loads(path.read_text());manifest['common']={**manifest.get('common',{}),**read_common(args.data)}
    path.write_text(json.dumps(manifest,indent=2)+'\n')
