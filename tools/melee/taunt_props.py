"""Taunt items embedded in fighter DATs, with their original item actions.

Dr. Mario: itDrMarioPill_Appeal_Spawn, item motion 2, root follows fighter.
Young Link: itClinkmilk, item action 0/1, bone 1 constrained to LThumbNb.
Visibility comes from each fighter's command-variable-1 window.
"""
import math,struct
from scene_assets import import_model,u32,roots
from dat_assets import fighter_bone_index

def build(code,data,common,kind,facing,armature,bones,taunt):
    if code not in ('Dr','Cl'):return None
    import bpy
    if code=='Cl':
        # PlCl also contains the hookshot article. Its two shared Link roots
        # are unrelated to the milk subtree selected below; do not expose
        # unresolved linked-list pointers as if they were local animations.
        data=bytearray(data)
        size,relocs,public,external=struct.unpack_from('>4I',data,4)
        table=32+size+relocs*4;strings=table+(public+external)*8
        for i in range(external):
            pointer,name=struct.unpack_from('>II',data,table+(public+i)*8)
            symbol=bytes(data[strings+name:data.index(0,strings+name)])
            if symbol not in (b'ItmLinkHShot_TopN_ACTION_Out_matanim_joint',b'ItmLinkHShot_TopN_ACTION_Out_shapeanim_joint'):
                raise ValueError(f'Unreviewed milk import external: {symbol}')
            seen=set()
            while 0<pointer<size and pointer not in seen:
                seen.add(pointer);next_pointer=u32(data,32+pointer)
                struct.pack_into('>I',data,32+pointer,0);pointer=next_pointer
        struct.pack_into('>I',data,16,0)
    root=next(iter(roots(data).values()))
    table=32+u32(data,root+0x48)
    article=32+u32(data,table+(1 if code=='Dr' else 5)*4)
    model=32+u32(data,article+16)
    state=32+u32(data,article+12)+(2 if code=='Dr' else (0 if facing=='right' else 1))*16
    before=set(bpy.data.objects)
    name=code+'-taunt-item'
    built=import_model(data,u32(data,model),u32(data,state),u32(data,state+4),name=name,max_frame=220)
    item=built[0]['armature'];objects=set(bpy.data.objects)-before
    item.rotation_euler.z=math.pi/2 if facing=='right' else -math.pi/2
    start=next(e['frame'] for e in taunt['events'] if e['opcode']==19 and e['fields']=={'Flag':1,'Value':1})
    end=next(e['frame'] for e in taunt['events'] if e['opcode']==19 and e['fields']=={'Flag':1,'Value':2})
    if code=='Cl':
        # Item starts when the bottle is requested (source frame 13).
        for action in built[0]['actions']:
            for layer in action.layers:
                for strip in layer.strips:
                    for bag in strip.channelbags:
                        for curve in bag.fcurves:
                            for key in curve.keyframe_points:
                                key.co.x+=start;key.handle_left.x+=start;key.handle_right.x+=start
        parts=32+u32(common,32+u32(common,roots(common)['ftLoadCommonData']+0x10)+kind*4)
        thumb=common[32+u32(common,parts+4)+31]
        target=bones[fighter_bone_index(common,kind,thumb)].name
        attached=list(item.pose.bones)[u32(data,model+8)]
        for kind in ['COPY_LOCATION','COPY_ROTATION']:
            constraint=attached.constraints.new(kind);constraint.target=armature;constraint.subtarget=target
            constraint.target_space='WORLD';constraint.owner_space='WORLD'
    return {'objects':objects,'start':start,'end':end,'source':f'Pl{code}.dat item action '+str(2 if code=='Dr' else (0 if facing=='right' else 1))}

def update(prop,frame,active):
    if not prop:return
    for obj in prop['objects']:
        if obj.type=='MESH':obj.hide_render=not(active and prop['start']<=frame<prop['end'])
