"""Expose embedded Melee map/effect models to the shared HAL DAT importer.

The data section and all relocation offsets stay untouched. Only the public
symbol table is replaced with the model/animation roots selected by the caller.
Layouts: HSDLib SBM_Map_Head, SBM_Map_GOBJ, SBM_ftLoadCommonData, SBM_EffectTable.
"""
import struct
from dat_assets import roots


def u32(data, offset):
    return struct.unpack_from('>I', data, offset)[0]


def expose_roots(data, specs):
    _, size, relocations, _, external = struct.unpack_from('>5I', data)
    if external:
        raise ValueError('External DAT references require resolution before import')
    entries, names = b'', b''
    for name, pointer, _ in specs:
        if not 0 < pointer < size:
            raise ValueError(f'Invalid embedded root: {name}')
        entries += struct.pack('>II', pointer, len(names))
        names += name.encode('ascii') + b'\0'
    result = bytearray(data[:32 + size + relocations * 4] + entries + names)
    struct.pack_into('>5I', result, 0, len(result), size, relocations, len(specs), 0)
    return result


def import_model(data, joint, animation=0, material=0, name='model', max_frame=60):
    import bpy
    from importer.phases.parse.parse import parse_sections
    from importer.phases.describe.describe import describe_scene
    from importer.phases.plan.plan import plan_scene
    from importer.phases.build_blender.build_blender import build_blender_scene
    from importer.phases.post_process.post_process import post_process
    install_tev_alpha_fix()
    install_vertex_alpha_animation_fix()
    specs = [(name + '_joint', joint, 'Joint')]
    if animation:
        specs.append((name + '_animjoint', animation, 'AnimationJoint'))
    if material:
        specs.append((name + '_matanim_joint', material, 'MaterialAnimationJoint'))
    options = {'filepath': name + '.dat', 'game': 'SMASH_BROS', 'max_frame': max_frame, 'section_names': []}
    wrapped = expose_roots(data, specs)
    sections = parse_sections(wrapped, {n: kind for n, _, kind in specs}, options)
    scene = describe_scene(sections, options)
    result = build_blender_scene(plan_scene(scene, options), bpy.context, options)
    post_process(set(), options=options, build_results=result)
    if material:
        # The pinned importer handles UV tracks but omits HSD_A_T_BLEND (9).
        # Landing dust starts at blend=0; omitting this track hides the puff.
        bind_texture_blends(sections, scene.models[0], name)
    if animation:
        bind_visibility(sections, scene.models[0], name, max_frame)
    return result


def install_vertex_alpha_animation_fix():
    """Retain authored material-alpha tracks even when GX selects vertex alpha.

    The entrance glow contains this combination. Its material alpha is not an
    input to the selected GX channel, but the importer still binds its tracks.
    Provide the unused animated value without changing the source alpha chain.
    """
    from importer.phases.plan.helpers import materials
    if getattr(materials,'_melee_vertex_alpha_fixed',False):return
    original=materials._plan_base_color_alpha
    def corrected(g, material, has_color_animation):
        result=original(g,material,has_color_animation)
        if has_color_animation and material.lighting!=materials.LightingModel.LIT and material.alpha_source==materials.ColorSource.VERTEX:
            node=g.add_node('ShaderNodeValue',name='AlphaValue')
            g.set_property(node,'_output_default',float(material.alpha))
        return result
    materials._plan_base_color_alpha=corrected
    materials._melee_vertex_alpha_fixed=True


def bind_visibility(sections, model, name, max_frame):
    """Apply HSD_A_J_NODE/BRANCH visibility, omitted by the pinned importer.

    Branch changes affect this node and its descendants, not its siblings.
    Sample in tree order, matching HSD_JObjAnimAll, so child tracks can override.
    """
    import bpy
    from importer.phases.describe.helpers.keyframe_decoder import decode_fobjdesc
    from bisect import bisect_right
    joint=next(s.root_node for s in sections if s.section_name==name+'_joint')
    anim=next(s.root_node for s in sections if s.section_name==name+'_animjoint')
    records=[]
    def visit(j, a):
        idx=len(records);record={'hidden':bool(j.flags & 16), 'tracks':[], 'end':idx+1}
        records.append(record)
        f=a.animation.frame if a and a.animation else None
        while f:
            if f.type in (11,12):record['tracks'].append((f.type,decode_fobjdesc(f)))
            f=f.next
        if j.child:visit(j.child,a.child if a else None)
        record['end']=len(records)
        if j.next:visit(j.next,a.next if a else None)
    visit(joint,anim)
    digits=len(str(max(len(model.meshes)-1,0)))
    for frame in range(max_frame+1):
        visible=[not r['hidden'] for r in records]
        for idx,record in enumerate(records):
            for kind,keys in record['tracks']:
                k=bisect_right([x.frame for x in keys],frame)-1
                if k<0:continue
                value=keys[k].value > .5
                for target in range(idx,record['end'] if kind==12 else idx+1):visible[target]=value
        for idx,bone in enumerate(model.bones):
            for mesh in bone.mesh_indices:
                obj=bpy.data.objects[f'{name}_mesh_{mesh:0{digits}}']
                obj.hide_render=not visible[idx]
                obj.keyframe_insert('hide_render',frame=frame)


def install_tev_alpha_fix():
    """Correct the pinned importer's Math socket indices for GX TEV alpha.

    Its color path uses MixRGB sockets 1/2. The alpha path accidentally uses
    those indices too, leaving Math input 0 at 0.5 and ignoring input 2.
    This makes transparent texels opaque (visible dust polygons / KO blocks).
    Keep the original combiner equation D +/- (A*(1-C) + B*C).
    """
    from importer.phases.plan.helpers import materials
    if getattr(materials, '_melee_alpha_fixed', False):
        return
    original = materials._plan_tev_add_sub
    def corrected(g, inputs, stage, is_color):
        if is_color:
            return original(g, inputs, stage, is_color)
        def math_node(op, a, b):
            n = g.add_node('ShaderNodeMath', properties={'operation': op})
            for i, value in enumerate([a, b]):
                if isinstance(value, tuple): g.add_link(value[0], value[1], n, i)
                else: g.set_input_default(n, i, value)
            return (n, 0)
        a, b, c, d = inputs
        blend = math_node('ADD', math_node('MULTIPLY', a, math_node('SUBTRACT', 1., c)),
                          math_node('MULTIPLY', b, c))
        return math_node('SUBTRACT' if stage.operation.value == 'SUBTRACT' else 'ADD', d, blend)
    materials._plan_tev_add_sub = corrected
    materials._melee_alpha_fixed = True


def bind_texture_blends(sections, model, name):
    import bpy
    from importer.phases.describe.helpers.keyframe_decoder import decode_fobjdesc
    joint=next(s.root_node for s in sections if s.section_name==name+'_joint')
    mat=next(s.root_node for s in sections if s.section_name==name+'_matanim_joint')
    digits=len(str(max(len(model.meshes)-1,0)))
    bone_index=0
    isolated_trees=set()
    def visit(joint, animated):
        nonlocal bone_index
        bone=model.bones[bone_index];bone_index+=1
        if animated and animated.animation:
            ma=animated.animation;dobj=joint.property;offset=0
            while ma and dobj:
                indices=[];pobj=dobj.pobject
                while pobj:
                    indices.append(bone.mesh_indices[offset]);offset+=1;pobj=pobj.next
                ta=ma.texture_animation
                while ta:
                    fobj=ta.animation.frame if ta.animation else None
                    while fobj:
                        if fobj.type==9:
                            keys=decode_fobjdesc(fobj)
                            for idx in indices:
                                material=bpy.data.objects[f'{name}_mesh_{idx:0{digits}}'].data.materials[0]
                                tree=material.node_tree
                                if tree.as_pointer() not in isolated_trees:
                                    # post_process attaches one multi-slot action
                                    # to every node tree. New keyframes otherwise
                                    # reuse its same NT slot and animate unrelated
                                    # nodes with the same generated name.
                                    tree.animation_data_clear()
                                    tree.animation_data_create().action=bpy.data.actions.new(material.name+'_texture_blend')
                                    isolated_trees.add(tree.as_pointer())
                                nodes=material.node_tree.nodes
                                mapping=nodes.get(f'TexMapping_{ta.id}')
                                if not mapping:raise ValueError('Missing animated texture mapping')
                                def depends(node, target):
                                    return node == target or any(depends(l.from_node, target) for socket in node.inputs for l in socket.links)
                                textures=[n for n in nodes if n.type=='TEX_IMAGE' and depends(n, mapping)]
                                blends=[n for n in nodes if n.type=='MIX_RGB' and n.blend_type=='MIX' and not n.inputs[0].is_linked
                                        and any(depends(n, texture) for texture in textures)]
                                # Replace/multiply layers do not consume the
                                # blending scalar, even if a stream animates it.
                                if not blends:continue
                                for node in blends:
                                    for key in keys:
                                        node.inputs[0].default_value=key.value
                                        node.inputs[0].keyframe_insert('default_value',frame=key.frame)
                                action=material.node_tree.animation_data.action
                                for curve in action.fcurves:
                                    for point,key in zip(curve.keyframe_points,keys):point.interpolation=key.interpolation.value
                        fobj=fobj.next
                    ta=ta.next
                ma=ma.next;dobj=dobj.next
        if joint.child:visit(joint.child,animated.child if animated else None)
        if joint.next:visit(joint.next,animated.next if animated else None)
    visit(joint,mat)


def stage_model(data, index):
    head = roots(data)['map_head']
    count = u32(data, head + 12)
    if not 0 <= index < count:
        raise ValueError('Stage group index out of range')
    group = 32 + u32(data, head + 8) + index * 0x34
    joint, anims, materials = struct.unpack_from('>3I', data, group)
    return joint, u32(data, 32 + anims) if anims else 0, u32(data, 32 + materials) if materials else 0


def respawn_model(data):
    common = roots(data)['ftLoadCommonData']
    platform = 32 + u32(data, common + 0x20)
    return (*struct.unpack_from('>2I', data, platform), 0)


def arrival_model(data):
    # fighter.c: Fighter_804D6514 = ftLoadCommonData->x40;
    # ftCo_800C6408 attaches this original trophy pedestal on EntryStart.
    common = roots(data)['ftLoadCommonData']
    return u32(data, common + 0x40), 0, 0


def effect_model(data, index):
    table = roots(data)['effCommonDataTable']
    duration, joint, anim, material, shape = struct.unpack_from('>f4I', data, table + 8 + index * 20)
    return (joint, anim, material), duration, shape


def has_shape_animation(data,pointer):
    """Some effect descriptors contain a shape tree with no animation payload."""
    visited=set()
    def visit(pointer):
        if not pointer:return False
        if pointer in visited or len(visited)>1024:raise ValueError('Invalid shape tree')
        visited.add(pointer)
        child,sibling,animation=__import__('struct').unpack_from('>3I',data,32+pointer)
        return bool(animation) or visit(child) or visit(sibling)
    return visit(pointer)
