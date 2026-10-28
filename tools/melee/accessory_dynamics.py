"""Bake the disc's accessory-bone solver into standalone preview clips.

Source: ftCo_8009CF84 / ftCo_8009E4A8 and lb_8001044C / lb_80011710.
Bowser hair and DK tie only. Uses original natural angles, angular limits,
convergence, gravity, damping, and DK's body collider. No external wind/attack
force fields or cross-clip physics history; clips start from a settled pose.
"""
import math
import struct
from dat_assets import roots, fighter_bone_index
from fighter_setup import model_scale

VERSION='disc-accessory-dynamics-v1'
SUPPORTED={'Dk','Kp'}

def read_setup(data):
    u=lambda p:struct.unpack_from('>I',data,p)[0]
    root=next(iter(roots(data).values()));dyn=32+u(root+0x2c)
    count,pointer=struct.unpack_from('>II',data,dyn)
    if not 0<=count<=10:raise ValueError('Invalid dynamics count')
    chains=[]
    for i in range(count):
        bone,params,n,*influence=struct.unpack_from('>3I3f',data,32+pointer+i*24)
        if not 2<=n<=32:raise ValueError('Invalid accessory chain length')
        chains.append({'bone':bone,'count':n,'influence':influence,
            'params':[list(struct.unpack_from('>15f',data,32+params+j*60)) for j in range(n)]})
    n,p=struct.unpack_from('>II',data,dyn+8)
    colliders=[]
    for i in range(n):
        bone,x,y,z,r=struct.unpack_from('>I4f',data,32+p+i*20)
        colliders.append({'bone':bone,'offset':[x,y,z],'radius':r})
    return {'chains':chains,'colliders':colliders,'lookup':u(dyn+16),'modelScale':model_scale(data)}

def active_prefix(data,setup,name):
    u=lambda p:struct.unpack_from('>I',data,p)[0]
    root=next(iter(roots(data).values()));table=32+u(root+12)
    for i in range(341):
        e=table+i*24;p=32+u(e)
        if not 32<=p<len(data):continue
        end=data.find(b'\0',p,min(len(data),p+256))
        if end<0 or not data[p:end].endswith(('_ACTION_'+name+'_figatree').encode()):continue
        flags=u(e+16)
        if flags & 0x10000000:return [c['count'] for c in setup['chains']]
        if flags & 0x08000000:
            if not setup['lookup']:raise ValueError('Missing motion dynamics lookup')
            slot=data[32+u(root+16)+i*2+1];ptr=u(32+setup['lookup']+slot*4)
            if not ptr:raise ValueError('Missing motion dynamics selection')
            return list(struct.unpack_from('>'+str(len(setup['chains']))+'I',data,32+ptr))
        return [0]*len(setup['chains'])
    raise ValueError(f'Missing dynamics motion flags for {name}')

def bake(model,data,common,kind,code):
    if code not in SUPPORTED:return None
    import bpy
    from mathutils import Vector,Matrix,Euler,Quaternion
    from shared.helpers.math_shim import compile_srt_matrix
    from shared.IR.animation import IRKeyframe
    from shared.IR.enums import Interpolation
    from importer.phases.build_blender.helpers.animations import _insert_raw_keyframes,_fill_missing_channels_with_rest
    setup=read_setup(data);bones=model.bones
    for chain in setup['chains']:
        ids=[fighter_bone_index(common,kind,chain['bone']+j) for j in range(chain['count'])]
        if any(bones[b].parent_index!=a for a,b in zip(ids,ids[1:])):raise ValueError('Accessory must be a contiguous child chain')
        chain['indices']=ids
    for c in setup['colliders']:c['index']=fighter_bone_index(common,kind,c['bone'])
    gs=setup['modelScale'];global_matrix=Matrix.Diagonal((gs,gs,gs,1))
    def unit(v,fallback=Vector((1,0,0))):return v.normalized() if v.length>1e-9 else fallback.copy()
    def angle(a,b):return math.acos(max(-1,min(1,unit(a).dot(unit(b)))))
    def toward(v,target,radians):
        axis=v.cross(target)
        if axis.length<1e-8:
            if v.dot(target)>0:return v.copy()
            axis=v.orthogonal()
        return Quaternion(unit(axis),radians)@v
    def srt(s,r,t):return compile_srt_matrix(s,r,t)
    def worlds(values):
        result=[];acc=[]
        for i,(s,r,t) in enumerate(values):
            parent=bones[i].parent_index
            pacc=acc[parent] if parent is not None else (gs,gs,gs)
            local=compile_srt_matrix(s,r,t,None if bones[i].flags&8 else pacc)
            result.append((result[parent] if parent is not None else global_matrix)@local)
            acc.append(tuple(s[j]*pacc[j] for j in range(3)))
        return result
    reports={}
    for animation in model.bone_animations:
        prefixes=active_prefix(data,setup,animation.name)
        action=bpy.data.actions.new('__accessory_source_'+animation.name)
        curves=[]
        for track in animation.tracks:
            raw=_insert_raw_keyframes(track,action);_fill_missing_channels_with_rest(track,action,raw);curves.append(raw)
        count=math.ceil(max(t.end_frame for t in animation.tracks))
        samples=[]
        for frame in range(count):
            samples.append([(tuple(c[j].evaluate(frame) for j in (7,8,9)),
                             tuple(c[j].evaluate(frame) for j in (0,1,2)),
                             tuple(c[j].evaluate(frame)*10 for j in (4,5,6))) for c in curves])
        bpy.data.actions.remove(action)
        active={i for ch,prefix in zip(setup['chains'],prefixes) for i in ch['indices'][prefix:]}
        rotations={i:Vector(bones[i].rotation) for i in active};vel={i:0. for i in active};axes={i:Vector((1,0,0)) for i in active}
        initial=worlds(samples[0]);previous={i:initial[i].translation.copy() for ch in setup['chains'] for i in ch['indices']}
        # lb_8000FD48 measures segment lengths in the loaded model's rest pose.
        rest=worlds([(b.scale,b.rotation,tuple(x*10 for x in b.position)) for b in bones])
        lengths={a:(rest[b].translation-rest[a].translation).length for ch in setup['chains'] for a,b in zip(ch['indices'],ch['indices'][1:])}
        output={i:[] for i in active};max_error=0.;collisions=0
        # Settle the standalone start; for looping clips run two full lead-in
        # cycles to retain motion-driven inertia across the exported loop seam.
        schedule=[(0,False)]*120+([(f,False) for _ in range(2) for f in range(count)] if animation.loop else [])+[(f,True) for f in range(count)]
        for frame,record in schedule:
            values=list(samples[frame])
            for i in active:values[i]=(bones[i].scale,rotations[i],tuple(x*10 for x in bones[i].position))
            world=worlds(values)
            colliders=[(world[c['index']]@Vector(c['offset']),c['radius']) for c in setup['colliders']]
            for chain,prefix in zip(setup['chains'],prefixes):
                ids=chain['indices'];influence=chain['influence']
                for j in range(prefix,len(ids)-1):
                    i,child=ids[j:j+2];params=chain['params'][j];s,r,t=values[i]
                    parent=world[bones[i].parent_index];pos=world[i].translation
                    natural_m=parent@srt(s,params[2:5],t)
                    offset=Vector(values[child][2])
                    natural=unit(natural_m@offset-pos)
                    current=unit(world[i]@offset-pos)
                    link=unit(previous[child]-pos,current);saved=link.copy();length=lengths[i]
                    stiffness=params[0]*influence[0]
                    if stiffness<1:link=toward(link,current,angle(link,current)*(1-stiffness))
                    gravity=influence[2]/length if length else 0
                    link=toward(link,Vector((0,-1,0)),abs(gravity*math.sin(angle(link,Vector((0,-1,0))))))
                    if vel[i]:link=Quaternion(axes[i],vel[i])@link
                    if gravity*length>0 and angle(saved,link)>params[14]:link=toward(saved,link,params[14])
                    if params[1]>0:link=toward(link,natural,min(angle(link,natural),params[1]))
                    deviation=angle(natural,link)
                    if deviation>params[6]:link=toward(link,natural,deviation-params[6])
                    # Original spherical body collider avoidance, with the
                    # game's 0.1-unit padding. No artist-authored collision mesh.
                    for center,radius in colliders:
                        delta=center-pos;distance=delta.length
                        tip=pos+link*length;edge=tip-pos
                        q=max(0,min(1,delta.dot(edge)/max(edge.length_squared,1e-12)))
                        if distance>radius and (pos+edge*q-center).length<radius+.1:
                            a=angle(delta,link);target=math.asin(min(1,(radius+.1)/distance))
                            if a>1e-8 and target>a:link=toward(unit(delta),link,target);collisions+=1
                    grounded=False
                    if code=='Dk' and animation.name not in ('Fall','DamageFlyN','DamageFlyRoll') and pos.y+link.y*length<0:
                        y=max(-1,min(1,-pos.y/length));horizontal=Vector((link.x,0,link.z));horizontal=unit(horizontal)
                        link=horizontal*math.sqrt(max(0,1-y*y))+Vector((0,y,0));grounded=True
                    speed=0 if grounded else angle(saved,link)
                    if speed>1e-8:axes[i]=unit(saved.cross(link),axes[i])
                    vel[i]=max(0,speed-params[13])
                    rotation=current.rotation_difference(link)
                    parent_q=parent.to_quaternion()
                    local_q=parent_q.inverted()@rotation@parent_q@Euler(r,'XYZ').to_quaternion()
                    euler=local_q.to_euler('XYZ',Euler(r,'XYZ'))
                    dominant=max(range(3),key=lambda k:abs(offset[k]));euler[dominant]*=.9
                    rotations[i]=Vector(euler);values[i]=(s,rotations[i],t)
                    # All downstream bones must see the solved parent this frame.
                    world=worlds(values)
                    previous[i]=pos.copy();previous[child]=world[child].translation.copy()
                    if record:max_error=max(max_error,angle(natural,unit(world[i]@offset-pos)))
                previous[ids[-1]]=world[ids[-1]].translation.copy()
            if record:
                for i in active:output[i].append(tuple(rotations[i]))
        for i,frames in output.items():
            track=animation.tracks[i]
            track.rotation=[[IRKeyframe(f,r[k],Interpolation.LINEAR) for f,r in enumerate(frames)] for k in range(3)]
            track.location=[[IRKeyframe(0,bones[i].position[k],Interpolation.CONSTANT)] for k in range(3)]
            track.scale=[[IRKeyframe(0,bones[i].scale[k],Interpolation.CONSTANT)] for k in range(3)]
        loop_delta=max((angle(Euler(frames[-1],'XYZ').to_matrix()@Vector((0,1,0)),Euler(frames[0],'XYZ').to_matrix()@Vector((0,1,0))) for frames in output.values()),default=0)
        reports[animation.name]={'loopSeamDirectionRadians':loop_delta,'animatedPrefix':prefixes,'frames':count,'maxDeviationRadians':max_error,'bodyCollisions':collisions}
    return {'version':VERSION,'source':'ftData.x2C / lb_8001044C','chains':setup['chains'],'colliders':setup['colliders'],
            'clips':reports,'settleFrames':120,'limitations':'Isolated clips; no cross-clip history, external force fields, or moving/sloped stage collision.'}
