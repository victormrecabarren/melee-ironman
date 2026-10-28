"""Runtime fighter setup omitted from raw model archives.

ftCommonAttributes +0x8C, Fighter_UpdateModelScale, ftGw_Init_OnLoad.
Uniform game scale is applied by the preview around the exported origin, keeping
full atlas resolution and separating gameplay size from export camera framing.
"""
import math
import struct
from dat_assets import roots

VERSION = 'disc-model-scale-v1'

def model_scale(data):
    root = next(iter(roots(data).values()))
    attrs = 32 + struct.unpack_from('>I', data, root)[0]
    scale = struct.unpack_from('>f', data, attrs + 0x8C)[0]
    if not math.isfinite(scale) or not .1 <= scale <= 4:
        raise ValueError(f'Invalid fighter model scale: {scale}')
    return scale

def gamewatch_attributes(data):
    root = next(iter(roots(data).values()))
    attrs = 32 + struct.unpack_from('>I', data, root + 4)[0]
    return {'width': struct.unpack_from('>f', data, attrs)[0],
            'color': list(data[attrs+4:attrs+8]), 'outline': list(data[attrs+20:attrs+24])}

def apply_gamewatch(model, armature, data):
    """Use the disc's separate outline meshes, costume RGBA, and flat depth."""
    import bpy
    from dat_assets import visibility_tables
    from fighter_materials import linear
    attrs = gamewatch_attributes(data)
    # Importer bakes Y-up -> Z-up; local X remains the game's depth axis.
    # Canvas applies the common model scale, but depth uses the absolute override.
    armature.scale.x = attrs['width'] / model_scale(data)
    outline = {i for group in visibility_tables(data,'Gw')[4] for alt in group for i in alt}
    materials = {}
    for name,rgba in [('body',attrs['color']),('outline',attrs['outline'])]:
        material=bpy.data.materials.new('GameWatch source '+name);material.use_nodes=True
        nodes=material.node_tree.nodes;nodes.clear()
        out=nodes.new('ShaderNodeOutputMaterial');mix=nodes.new('ShaderNodeMixShader')
        transparent=nodes.new('ShaderNodeBsdfTransparent');emission=nodes.new('ShaderNodeEmission')
        emission.inputs['Color'].default_value=tuple(linear(c/255) for c in rgba[:3])+(1,)
        mix.inputs[0].default_value=rgba[3]/255
        links=material.node_tree.links
        links.new(transparent.outputs[0],mix.inputs[1]);links.new(emission.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],out.inputs['Surface'])
        materials[name]=material
    body_collection=bpy.data.collections.new('GameWatch body');bpy.context.scene.collection.children.link(body_collection)
    outline_collection=bpy.data.collections.new('GameWatch outline');bpy.context.scene.collection.children.link(outline_collection)
    digits=len(str(max(len(model.meshes)-1,0)))
    for i,mesh in enumerate(model.meshes):
        obj=bpy.data.objects[f'PlGwNr_mesh_{i:0{digits}}']
        is_outline=mesh.source_dobj in outline
        obj.data.materials.clear();obj.data.materials.append(materials['outline' if is_outline else 'body'])
        for collection in list(obj.users_collection): collection.objects.unlink(obj)
        (outline_collection if is_outline else body_collection).objects.link(obj)
    # ftDrawCommon_80080E18 renders outlines without Z writes, then body over
    # them. Separate render layers preserve that order even on overlapping parts.
    scene=bpy.context.scene
    body_layer=scene.view_layers[0];body_layer.name='GameWatch body'
    outline_layer=scene.view_layers.new('GameWatch outline')
    body_layer.layer_collection.children[outline_collection.name].exclude=True
    outline_layer.layer_collection.children[body_collection.name].exclude=True
    scene.use_nodes=True;nodes=scene.node_tree.nodes;nodes.clear()
    body_node=nodes.new('CompositorNodeRLayers');body_node.layer=body_layer.name
    outline_node=nodes.new('CompositorNodeRLayers');outline_node.layer=outline_layer.name
    over=nodes.new('CompositorNodeAlphaOver');out=nodes.new('CompositorNodeComposite')
    links=scene.node_tree.links
    links.new(outline_node.outputs['Image'],over.inputs[1]);links.new(body_node.outputs['Image'],over.inputs[2]);links.new(over.outputs[0],out.inputs[0])
    return {**attrs,'version':'disc-gamewatch-setup-v1','outlineSource':'original DObjs from ftData.x48_items[10]'}
