"""Small, bounded readers for the user's local Melee data (no ROM bundled).

Layouts cross-checked against HSDLib's HSD_FigaTree / HSD_Track and
SBM_PlayerModelLookupTables, and doldecomp/melee's ftparts.c.
"""
import struct
from pathlib import Path
from types import SimpleNamespace


def fighter_bone_index(common, kind, part):
    """ftParts_SetupParts skips PlCo.x14 slots reserved for attached models.

    DAT hitboxes/effect attachments use the sparse game parts array; model and
    animation joints use compact DFS order. Kirby reserves 13 copy-ability slots.
    """
    u = lambda p: struct.unpack_from('>I', common, p)[0]
    table = 32 + u(roots(common)['ftLoadCommonData'] + 0x14)
    descriptor = u(table + kind * 4)
    if not descriptor:
        return part
    pointer, count = struct.unpack_from('>II', common, 32 + descriptor)
    if count > 32:
        raise ValueError('Invalid reserved fighter parts table')
    reserved = {common[32 + pointer + i * 4] for i in range(count)}
    if part in reserved:
        raise ValueError(f'Part {part} belongs to an attached model, not the base skeleton')
    return part - sum(slot < part for slot in reserved)


def roots(data):
    size, length, relocations, public, external = struct.unpack_from('>5I', data)
    table = 32 + length + relocations * 4
    strings = table + (public + external) * 8
    if size > len(data) or strings > size:
        raise ValueError('Invalid DAT header')
    result = {}
    for i in range(public):
        pointer, name = struct.unpack_from('>II', data, table + i * 8)
        name += strings
        result[data[name:data.index(0, name, size)].decode('ascii')] = pointer + 32
    return result


def animations(path):
    data = Path(path).read_bytes()
    offset = 0
    while offset + 32 <= len(data):
        size = struct.unpack_from('>I', data, offset)[0]
        if size < 32 or offset + size > len(data):
            raise ValueError(f'Invalid animation archive at {offset:#x}')
        archive = data[offset:offset + size]
        for name, root in roots(archive).items():
            if '_ACTION_' in name and name.endswith('_figatree'):
                yield name.split('_ACTION_', 1)[1][:-9], archive, root
        offset = (offset + size + 31) & ~31


def animation_set(name, data, root, bones):
    from shared.IR.animation import IRBoneAnimationSet, IRBoneTrack
    from importer.phases.describe.helpers.keyframe_decoder import decode_fobjdesc
    frame_count, counts, tracks = struct.unpack_from('>fII', data, root + 8)
    counts += 32
    tracks += 32
    count = data.index(255, counts) - counts
    if count != len(bones):
        raise ValueError(f'{name}: animation has {count} joints, model has {len(bones)}')
    result = IRBoneAnimationSet(name=name, loop=name in ('Wait', 'Wait1', 'Fall'))
    for index, bone in enumerate(bones):
        channels = [[[], [], []] for _ in range(3)]
        for _ in range(data[counts + index]):
            length, start, kind, vf, tf, _, pointer = struct.unpack_from('>Hh4BI', data, tracks)
            tracks += 12
            if kind not in (1, 2, 3, 5, 6, 7, 8, 9, 10):
                continue
            category, axis = (0, kind - 1) if kind <= 3 else ((1, kind - 5) if kind <= 7 else (2, kind - 8))
            stream = SimpleNamespace(raw_ad=data[32 + pointer:32 + pointer + length],
                                     start_frame=start, frac_value=vf, frac_slope=tf)
            channels[category][axis] = decode_fobjdesc(stream, scale=.1 if category == 1 else 1)
        result.tracks.append(IRBoneTrack(
            bone.name, index, *channels, rest_local_matrix=bone.local_matrix,
            rest_rotation=bone.rotation, rest_position=bone.position,
            rest_scale=bone.scale, end_frame=frame_count))
    return result, frame_count


def visibility_tables(data, code):
    u = lambda offset: struct.unpack_from('>I', data, offset + 32)[0]
    root = next(iter(roots(data).values())) - 32
    lookup = u(root + 8)
    group_count, tables = u(lookup), u(lookup + 4)
    if group_count > 11:
        raise ValueError('Unexpected fighter visibility table')
    pointers={i:u(tables+i*4) for i in (0,1,3)}
    if code=='Gw': pointers[4]=u(u(root+0x48)+10*4)
    parsed={}
    for index,table in pointers.items():
        if not table: continue
        groups=[]
        for group in range(group_count):
            count,entries=u(table+group*8),u(table+group*8+4)
            groups.append([data[32+u(entries+a*8+4):32+u(entries+a*8+4)+u(entries+a*8)] for a in range(count)])
        parsed[index]=groups
    return parsed


def visibility(data, code, overrides=None):
    parsed=visibility_tables(data,code)
    selected=[0]*len(parsed[0])
    if code=='Fe': selected[2]=-1
    if code=='Pe': selected[3]=-1
    if code=='Gw': selected=[0,-1,0,0,-1,-1,-1,-1,-1,-1,-1] # ftGw_Init_OnDeath
    for group,value in (overrides or {}).items():
        if not 0 <= group < len(selected): raise ValueError('Invalid model state group')
        selected[group]=value
    visible={i:False for groups in parsed.values() for alts in groups for ordinals in alts for i in ordinals}
    # G&W uses separate body and outline draw passes (ftDrawCommon), all from DAT.
    for table in ((0,1,4) if code=='Gw' else (0,)):
        for group, alternatives in enumerate(parsed.get(table, [])):
            for alternative, ordinals in enumerate(alternatives):
                if alternative==selected[group]:
                    for ordinal in ordinals: visible[ordinal]=True
    return visible


def apply_visibility(model, joint, visible):
    """Translate the game's DObj ordinals to the importer's per-PObj meshes."""
    from shared.Constants.gx import GX_VA_POS
    mesh_index = dobj_index = 0

    def walk(joint):
        nonlocal mesh_index, dobj_index
        dobj = joint.property
        if dobj and hasattr(dobj, 'pobject'):
            while dobj:
                polygon = dobj.pobject
                while polygon:
                    if polygon.find_attribute_index(GX_VA_POS) is not None:
                        model.meshes[mesh_index].is_hidden = not visible.get(dobj_index, True)
                        model.meshes[mesh_index].source_dobj = dobj_index
                        mesh_index += 1
                    polygon = polygon.next
                dobj_index += 1
                dobj = dobj.next
        if joint.child and not joint.flags & 4096:
            walk(joint.child)
        if joint.next:
            walk(joint.next)

    walk(joint)
    if mesh_index != len(model.meshes):
        raise ValueError('Mesh visibility mapping did not cover the model')
