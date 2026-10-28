import tempfile,unittest
from pathlib import Path
from PIL import Image,ImageChops
from compact_fighters import compact_clip,PAGE

class CompactFightersTest(unittest.TestCase):
    def test_roundtrip_preserves_pixels_offsets_duplicates_and_page_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory);atlas=Image.new('RGBA',(4096,384*4))
            for i in range(32):
                tile=Image.new('RGBA',(500,370),(20+i,130,210,255))
                if i==1:tile=Image.new('RGBA',(500,370),(20,130,210,255))
                atlas.paste(tile,(i%8*512+5,i//8*384+7))
            atlas.save(folder/'source.webp',lossless=True)
            clip=compact_clip(folder,{'file':'source.webp','frames':32})
            self.assertGreater(len(clip['pages']),1)
            pages=[Image.open(folder/p['file']).convert('RGBA') for p in clip['pages']]
            self.assertTrue(all(im.width<=PAGE and im.height<=PAGE for im in pages))
            self.assertEqual(clip['rects'][0],clip['rects'][1])
            for i,(page,x,y,w,h,dx,dy) in enumerate(clip['rects']):
                reconstructed=Image.new('RGBA',(512,384));reconstructed.paste(pages[page].crop((x,y,x+w,y+h)),(dx,dy))
                source=atlas.crop((i%8*512,i//8*384,i%8*512+512,i//8*384+384))
                self.assertEqual(source.tobytes(),reconstructed.tobytes())
if __name__=='__main__':unittest.main()
