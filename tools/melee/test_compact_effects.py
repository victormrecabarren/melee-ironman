"""Run with python3 -m unittest discover -s tools/melee -p test_compact_effects.py."""
import unittest
import numpy as np
from PIL import Image
from compact_effects import screen_alpha


class CompactEffectsTest(unittest.TestCase):
    def test_screen_contribution_is_preserved(self):
        pixels=np.random.default_rng(7).integers(0,256,(64,64,4),dtype=np.uint8)
        actual=np.array(screen_alpha(Image.fromarray(pixels))).astype(float)
        before=pixels[:,:,:3].astype(float)*pixels[:,:,3:4]/255
        after=actual[:,:,:3]*actual[:,:,3:4]/255
        # At most one 8-bit quantization step after alpha/color factoring.
        self.assertLessEqual(np.abs(before-after).max(),1)

    def test_black_screen_padding_becomes_empty_without_losing_color(self):
        im=Image.new('RGBA',(16,16),(0,0,0,255));im.putpixel((6,9),(20,30,255,255))
        out=screen_alpha(im)
        self.assertEqual(out.getchannel('A').getbbox(),(6,9,7,10))
        self.assertEqual(out.getpixel((6,9)),(20,30,255,255))

if __name__=='__main__':unittest.main()
