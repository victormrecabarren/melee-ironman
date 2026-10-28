"""Guard against exporting an emitter-only effect as invisible black mesh frames."""
import json,unittest
from pathlib import Path
from PIL import Image
import numpy as np
ROOT=Path(__file__).resolve().parents[2]/'public/melee-preview'
class NormalImpactTest(unittest.TestCase):
    def test_original_emitter_burst_is_visible_colored_and_unclipped(self):
        clip=json.loads((ROOT/'manifest.json').read_text())['environment']['normal-impact']
        self.assertIn('generators 2 / 306 / 307',clip['source'])
        atlas=Image.open(ROOT/clip['file']).convert('RGBA')
        self.assertLess(atlas.width*atlas.height*4,16*1024*1024)
        colors=[]
        for i,rect in enumerate(clip['rects']):
            x,y,w,h,dx,dy=rect
            if not w or not h:continue
            self.assertGreater(dx,1);self.assertGreater(dy,1)
            self.assertLess(dx+w,clip['width']-1);self.assertLess(dy+h,clip['height']-1)
            pixels=np.array(atlas.crop((x,y,x+w,y+h))).astype(float)
            energy=(pixels[:,:,:3]*pixels[:,:,3:4]/255).sum(axis=(0,1))
            if i<8:
                self.assertGreater(energy.sum(),10000)
                colors.append(energy)
        self.assertEqual(len(colors),8)
        # Distinct red, blue and green frames, not just an alpha silhouette.
        dominant={int(np.argmax(c)) for c in colors}
        self.assertEqual(dominant,{0,1,2})
if __name__=='__main__':unittest.main()
