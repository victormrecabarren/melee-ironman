import json,unittest
from pathlib import Path
from fighter_setup import model_scale,gamewatch_attributes
from dat_assets import visibility,visibility_tables
DATA=Path('/private/tmp/melee-asset-test')

@unittest.skipUnless((DATA/'PlGw.dat').exists(),'requires local extracted game data')
class FighterSetupTest(unittest.TestCase):
    def test_all_published_scales_equal_original_data(self):
        m=json.loads((Path(__file__).parents[2]/'public/melee-preview/manifest.json').read_text())
        for key,f in m['fighters'].items():
            with self.subTest(fighter=key):self.assertEqual(f['modelScale'],model_scale((DATA/f"Pl{f['code']}.dat").read_bytes()))
    def test_gamewatch_default_parts_and_original_outline(self):
        d=(DATA/'PlGw.dat').read_bytes();v=visibility(d,'Gw');tables=visibility_tables(d,'Gw')
        self.assertEqual(gamewatch_attributes(d)['color'],[0,0,0,255])
        self.assertEqual(gamewatch_attributes(d)['outline'],[255,255,255,128])
        for table in (0,1,4):
            for group,alts in enumerate(tables[table]):
                for alternative,ordinals in enumerate(alts):
                    for ordinal in ordinals:self.assertEqual(v[ordinal],group in (0,2,3) and alternative==0)
        changed=visibility(d,'Gw',{2:1})
        self.assertTrue(changed[16]);self.assertFalse(changed[17])
        self.assertTrue(changed[2]);self.assertFalse(changed[3])
if __name__=='__main__':unittest.main()
