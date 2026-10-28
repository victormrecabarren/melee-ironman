"""Pose original hit spheres and idle hurt capsules in facing-relative game units.

Source layouts: ftData.x30 / ftHurtboxInit, ftAction spawn_hitbox, ftColl.
This is spacing metadata for the staged preview, not a full collision engine.
"""
import struct
from dat_assets import roots, fighter_bone_index

VERSION = 'posed-hitboxes-v1'

def hurtboxes(data):
    root=next(iter(roots(data).values()))
    table=32+struct.unpack_from('>I',data,root+0x30)[0]
    count,pointer=struct.unpack_from('>II',data,table)
    if not 0<count<=15:raise ValueError('Invalid hurtbox count')
    result=[]
    for i in range(count):
        bone,height,grabbable,*values=struct.unpack_from('>3I7f',data,32+pointer+i*40)
        result.append({'bone':bone,'height':height,'a':values[:3],'b':values[3:6],'radius':values[6]})
    return result

def sample_geometry(scene,armature,model,fighter,data,common=None):
    from mathutils import Vector
    direction=1 if fighter['facing']=='right' else -1
    def point(bone,offset):
        if common is not None:bone=fighter_bone_index(common,fighter['kind'],bone)
        matrix=armature.matrix_world @ armature.pose.bones[model.bones[bone].name].matrix
        p=matrix @ Vector(offset)
        return [round(direction*p.x*10,4),round(p.z*10,4),round(p.y*10,4)]
    def action(name):
        import bpy
        a=bpy.data.actions[name];armature.animation_data.action=a;armature.animation_data.action_slot=a.slots[0]
    action(fighter['clips']['idle']['source']);scene.frame_set(0)
    hurt=[{'bone':h['bone'],'a':point(h['bone'],[x*.1 for x in h['a']]),
           'b':point(h['bone'],[x*.1 for x in h['b']]),'radius':round(h['radius'],4)} for h in hurtboxes(data)]
    action(fighter['clips']['smash']['source'])
    move=fighter['move'];active={};frames=[]
    for frame in range(move['activeEnd']+1):
        scene.frame_set(frame)
        for e in move['events']:
            if e['frame']!=frame:continue
            if e['opcode']==11:active[e['fields']['ID']]=e['fields']
            elif e['opcode']==16:active.clear()
            elif e['opcode'] in (12,13,14,15):raise ValueError('Hitbox mutation needs geometry decoder support')
        if not active:continue
        spheres=[]
        for h in active.values():
            if h['Use Common Bone IDs']:raise ValueError('Common bone mapping required')
            offset=[h[k]*.1/256 for k in ['Z-Offset','Y-Offset','X-Offset']]
            spheres.append({'id':h['ID'],'center':point(h['Bone'],offset),'radius':h['Size']/256,
                            'damage':h['Damage'],'element':h['Element']})
        frames.append({'frame':frame,'spheres':spheres})
    return {'version':VERSION,'units':'facing-relative game units: forward, up, depth',
            'hurtPose':'idle frame 0','hurtCapsules':hurt,'hitFrames':frames,
            'maxReach':round(max(h['center'][0]+h['radius'] for f in frames for h in f['spheres']),4)}
