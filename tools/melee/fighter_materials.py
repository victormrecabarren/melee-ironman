"""Source-aware highlight conversion for fighter exports (Blender 4.x).

GX specular color controls highlight color/amplitude; shininess shapes the
attenuation lobe. The importer's legacy scalar tint inversion loses dark/tinted
specular colors on Blender 4's COLOR socket. These are separate parameters.
The GGX lobe is a half-width approximation to HSD_LObjSetup's GX attenuation,
not a complete reproduction of GX vertex lighting / the stage light rig.
"""
import math

MATERIAL_VERSION='source-specular-v1'

def linear(c):
    return c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4

def parameters(material):
    k=max(0.,float(material.shininess))*.5
    half_cos2=k/(k+1)
    roughness=((1-half_cos2)/(math.sqrt(2)-half_cos2))**.25
    return {'Specular IOR Level':.5 if material.enable_specular else 0.,
            'Specular Tint':tuple(linear(float(c)) for c in material.specular_color[:3])+(1.,),
            'Roughness':roughness}

def apply(model,prefix):
    import bpy
    digits=len(str(max(len(model.meshes)-1,0)));audit=[]
    for i,mesh in enumerate(model.meshes):
        if mesh.material is None:continue
        obj=bpy.data.objects.get(f'{prefix}_mesh_{i:0{digits}}')
        if obj is None:raise ValueError(f'Missing source mesh {prefix}/{i}')
        values=parameters(mesh.material)
        for material in obj.data.materials:
            if not material or not material.use_nodes:continue
            for node in material.node_tree.nodes:
                if node.type!='BSDF_PRINCIPLED':continue
                for name,value in values.items():
                    if node.inputs[name].is_linked:raise ValueError(f'Unexpected animated/linked {name}: {material.name}')
                    node.inputs[name].default_value=value
                material['melee_material_version']=MATERIAL_VERSION
        audit.append({'mesh':i,'specularEnabled':mesh.material.enable_specular,
                      'specularColor':list(mesh.material.specular_color),'shininess':mesh.material.shininess,
                      'converted':values})
    return audit
