"""Original Link/Young Link input follow-up, sampled at the earliest legal input.

ftattacks4combo.c: cmd_vars[0] plus A enters AttackS42 at source frame zero.
The first script enables this at 19 (Link) / 20 (Young Link). Hitlag pauses
these action clocks separately in the browser; it is not baked into sprites.
"""
from copy import deepcopy
from pathlib import Path
from move_data import read_move


def read_preview_move(path, action):
    first = read_move(path, action)
    if Path(path).stem not in ('PlLk', 'PlCl') or action != 'AttackS41':
        return first
    gate = next(e['frame'] for e in first['events'] if e['opcode'] == 19
                and e['fields'] == {'Flag':0, 'Value':1})
    second = read_move(path, 'AttackS42')
    result = deepcopy(first)
    result['action'] = 'AttackS41+AttackS42'
    result['sequence'] = [
        {'action':'AttackS41', 'start':0, 'end':gate, 'actionIndex':first['actionIndex']},
        {'action':'AttackS42', 'start':gate, 'actionIndex':second['actionIndex']}]
    result['transition'] = 'earliest A input permitted by cmd_vars[0]; ftCo_800CECE8'
    # State changes clear the old hitboxes and model commands. No first-swing
    # recovery commands may leak into the follow-up's action clock.
    result['events'] = [e for e in result['events'] if e['frame'] < gate and e['opcode'] != 0]
    result['events'].append({'frame':gate, 'opcode':16, 'name':'Remove All Hitboxes', 'fields':{}})
    result['events'] += [{**e, 'frame':e['frame']+gate} for e in second['events']]
    result['hitboxes'] += second['hitboxes']
    result['hitPhases'] += [{**h, 'frame':h['frame']+gate} for h in second['hitPhases']]
    result['activeEnd'] = gate+second['activeEnd']
    if 'trail' in first and 'trail' in second:
        result['trail']['ranges'] = [
            [first['trail']['start'], min(gate, first['trail']['end'])],
            [gate+second['trail']['start'], gate+second['trail']['end']]]
    return result


def combine_animations(parts, move):
    """Sample decoded source channels at 60 Hz, retaining rest-only channels.

    Sampling before the importer's rest-matrix conversion keeps the same model
    space for both actions. Each source gets a fresh channel evaluation; no
    interpolation bridges the state change.
    """
    import bpy
    from shared.IR.animation import IRKeyframe
    from shared.IR.enums import Interpolation
    from importer.phases.build_blender.helpers.animations import _insert_raw_keyframes, _fill_missing_channels_with_rest
    import math
    sequence = move['sequence']
    result = deepcopy(parts[sequence[0]['action']][0])
    result.name = move['action']
    result.loop = False
    total = sequence[-1]['start']+math.ceil(parts[sequence[-1]['action']][1])
    for track in result.tracks:
        track.rotation = [[], [], []]
        track.location = [[], [], []]
        track.scale = [[], [], []]
        track.end_frame = total
    for segment in sequence:
        source, duration = parts[segment['action']]
        count = segment.get('end', segment['start']+math.ceil(duration))-segment['start']
        action = bpy.data.actions.new('__sequence_source_'+source.name)
        for track, output in zip(source.tracks, result.tracks):
            curves = _insert_raw_keyframes(track, action)
            _fill_missing_channels_with_rest(track, action, curves)
            for channels, indices in [(output.rotation,(0,1,2)), (output.location,(4,5,6)), (output.scale,(7,8,9))]:
                for axis, index in enumerate(indices):
                    channels[axis] += [IRKeyframe(frame=segment['start']+f, value=curves[index].evaluate(f),
                        interpolation=Interpolation.LINEAR) for f in range(count)]
        bpy.data.actions.remove(action)
    return result, total
