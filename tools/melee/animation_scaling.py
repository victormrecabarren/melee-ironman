"""Keep classical joint scale in the pose matrix, as HSD_JObjMakeMatrix does.

The pinned importer conflates the accumulated scale used for the child's
correction with the actual world matrix. Classical joints copy parent `scl`,
but their own animated scale must still enter their SRT matrix (Mario's taunt).
"""
def install():
    from mathutils import Matrix
    from shared.helpers.math_shim import compile_srt_matrix,matrix_to_list
    import importer.phases.build_blender.helpers.animations as animations
    original=animations.bake_frame
    def bake(skeleton,srts,indices):
        if not any(b.classical_scaling and i in srts and any(abs(srts[i][0][j]-b.rest_scale[j])>1e-6 for j in range(3)) for i,b in enumerate(skeleton.bones)):
            return original(skeleton,srts,indices)
        world={};accum={};result={}
        for i in skeleton.dfs_order:
            b=skeleton.bones[i];parent=b.parent_index
            s,r,t=srts.get(i,(b.rest_scale,b.rest_rotation,b.rest_position))
            inherited=accum.get(parent)
            local=compile_srt_matrix(s,r,t,inherited)
            world[i]=world[parent]@local if parent is not None else local
            accum[i]=inherited if b.classical_scaling else tuple((lambda v: v if abs(v)>=1e-4 else (-1e-4 if v<0 else 1e-4))(s[j]*(inherited[j] if inherited else 1)) for j in range(3))
            if i in indices:result[i]=matrix_to_list(world[i]@Matrix(b.rest_world_matrix).inverted_safe()@Matrix(b.normalized_rest_matrix))
        return result
    animations.bake_frame=bake
