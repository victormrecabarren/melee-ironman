"""Melee's three-sample sword afterimage, from ftAfterImage and DAT attrs.

This is generated geometry in the game, not a stored texture. Preserve the
source blade endpoints, colors, alpha range, 3-frame history and 5-degree arcs.
"""
import math


class SwordTrail:
    def __init__(self, armature, bones, desc):
        import bpy
        self.armature, self.bones, self.desc = armature, bones, desc
        self.mesh = bpy.data.meshes.new('Original sword afterimage')
        self.obj = bpy.data.objects.new('Original sword afterimage', self.mesh)
        bpy.context.collection.objects.link(self.obj)
        mat = bpy.data.materials.new('DAT afterimage vertex colors'); mat.use_nodes = True
        tree = mat.node_tree; tree.nodes.clear()
        vertex = tree.nodes.new('ShaderNodeVertexColor'); vertex.layer_name = 'Color'
        emission = tree.nodes.new('ShaderNodeEmission')
        transparent = tree.nodes.new('ShaderNodeBsdfTransparent')
        mix = tree.nodes.new('ShaderNodeMixShader'); output = tree.nodes.new('ShaderNodeOutputMaterial')
        tree.links.new(vertex.outputs['Color'], emission.inputs['Color'])
        tree.links.new(vertex.outputs['Alpha'], mix.inputs[0])
        tree.links.new(transparent.outputs[0], mix.inputs[1]); tree.links.new(emission.outputs[0], mix.inputs[2])
        tree.links.new(mix.outputs[0], output.inputs['Surface'])
        self.mesh.materials.append(mat)

    def update(self, scene, frame):
        from mathutils import Vector
        d = self.desc
        active = next(((start,end) for start,end in d.get('ranges', [[d['start'],d['end']]])
                       if start+1 <= frame < end), None)
        self.obj.hide_render = active is None
        if self.obj.hide_render:
            return
        samples = []
        for time in range(frame, max(active[0]-1, frame-3), -1):
            scene.frame_set(time)
            bone = self.armature.pose.bones[self.bones[d['bone']].name]
            m = self.armature.matrix_world @ bone.matrix
            samples.append((m.translation.copy(), (m.to_3x3() @ Vector((1,0,0))).normalized()))
        scene.frame_set(frame)
        top, bottom = d['top']*.1, d['bottom']*.1
        distances = [0]
        for i in range(1, len(samples)):
            a, b = samples[i-1], samples[i]
            distances.append(distances[-1] + ((a[0]+a[1]*top)-(b[0]+b[1]*top)).length)
        total = max(.00001, distances[-1])
        verts, colors = [], []
        def linear(c):
            c /= 255
            return c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4
        def pair(pos, direction, f):
            alpha = (d['alphaEnd'] + f*(d['alphaStart']-d['alphaEnd']))/255
            for offset, shrink, color in [(bottom,d['innerShrink'],d['innerColor']), (top,d['outerShrink'],d['outerColor'])]:
                old = bottom + shrink*(top-bottom)
                verts.append(pos + direction*(old+f*(offset-old)))
                colors.append((*[linear(c) for c in color],alpha))
        for i,(pos,direction) in enumerate(samples):
            f = 1-distances[i]/total
            pair(pos,direction,f)
            if i+1 < len(samples):
                next_pos,next_dir=samples[i+1]
                steps=max(1,int(direction.angle(next_dir)/math.radians(5))+1)
                for j in range(1,steps):
                    t=j/steps
                    pair(pos.lerp(next_pos,t),direction.slerp(next_dir,t),f+(1-distances[i+1]/total-f)*t)
        faces=[(i,i+1,i+3,i+2) for i in range(0,len(verts)-2,2)]
        self.mesh.clear_geometry(); self.mesh.from_pydata(verts,[],faces); self.mesh.update()
        layer=self.mesh.color_attributes.get('Color') or self.mesh.color_attributes.new(name='Color',type='FLOAT_COLOR',domain='POINT')
        for i,color in enumerate(colors):layer.data[i].color=color
