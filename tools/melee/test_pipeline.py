"""Regression checks for the original effect transparency and color VM.
Run in the bpy runtime with the importer on PYTHONPATH; no disc or rendering needed.
"""
import struct
import unittest
from common_states import color_cycle
from scene_assets import install_tev_alpha_fix, has_shape_animation
from move_data import decode_script


class AlphaGraph:
    def __init__(self): self.nodes = {}; self.inputs = {}
    def add_node(self, kind, properties):
        name = str(len(self.nodes)); self.nodes[name] = properties['operation']; self.inputs[name] = {}; return name
    def add_link(self, source, socket, target, slot): self.inputs[target][slot] = (source, socket)
    def set_input_default(self, target, slot, value): self.inputs[target][slot] = value
    def evaluate(self, ref):
        if not isinstance(ref, tuple): return ref
        name = ref[0]; values = self.inputs[name]
        # The third Math socket is unused for these binary operations.
        a, b = [self.evaluate(values.get(i, .5)) for i in [0, 1]]
        return {'ADD': lambda: a+b, 'SUBTRACT': lambda: a-b, 'MULTIPLY': lambda: a*b}[self.nodes[name]]()


class PipelineRegression(unittest.TestCase):
    def test_bounded_move_loop_preserves_repeated_event_timing(self):
        data=bytearray(64)
        # Loop three times: wait two frames, then clear hitboxes.
        words=[3<<26|3,1<<26|2,16<<26,4<<26,0]
        for i,word in enumerate(words):struct.pack_into('>I',data,32+i*4,word)
        events=decode_script(data,32)
        self.assertEqual([e['frame'] for e in events if e['opcode']==16],[2,4,6])
        struct.pack_into('>I',data,32,4<<26)
        with self.assertRaisesRegex(ValueError,'Loop end'):decode_script(data,32)

    def test_empty_shape_tree_is_not_a_missing_morph_animation(self):
        data=bytearray(128)
        struct.pack_into('>3I',data,48,32,0,0)
        self.assertFalse(has_shape_animation(data,16))
        struct.pack_into('>I',data,72,80)
        self.assertTrue(has_shape_animation(data,16))

    def test_transparent_texels_stay_transparent(self):
        from types import SimpleNamespace
        from importer.phases.plan.helpers import materials
        install_tev_alpha_fix()
        for tex_alpha in [0., .25, 1.]:
            graph = AlphaGraph()
            refs=[]
            for value in [0., 0., 0., tex_alpha]:
                node=graph.add_node('ShaderNodeMath', {'operation':'ADD'})
                graph.set_input_default(node,0,value);graph.set_input_default(node,1,0.);refs.append((node,0))
            output=materials._plan_tev_add_sub(graph,refs,SimpleNamespace(operation=SimpleNamespace(value='ADD')),False)
            self.assertAlmostEqual(graph.evaluate(output), tex_alpha)

    def test_electric_loop_subroutine_and_end_do_not_repeat_forever(self):
        data=bytearray(128)
        struct.pack_into('>I', data, 0, 0)  # color table points at data-section 0
        # Loop twice: call blue/white blink, then return. End disables playback.
        words=[3<<26|2,5<<26,48,4<<26,10<<26]
        for i,w in enumerate(words):struct.pack_into('>I',data,32+4*i,w)
        sub=[18<<26,0x0000945a,11<<26|1,18<<26,0xffffff46,11<<26|1,6<<26]
        for i,w in enumerate(sub):struct.pack_into('>I',data,80+4*i,w)
        result=color_cycle(data,0,0,6)
        self.assertEqual(result['rgba'],[[0,0,148,90],[255,255,255,70]]*2+[[0,0,0,0]]*2)

if __name__ == '__main__': unittest.main()
