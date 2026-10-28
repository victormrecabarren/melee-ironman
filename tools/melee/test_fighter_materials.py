import math,unittest
from types import SimpleNamespace
from fighter_materials import parameters,linear

class FighterMaterialTests(unittest.TestCase):
    def material(self,color=(.149,.149,.149,1),shininess=50,enabled=True):
        return SimpleNamespace(specular_color=color,shininess=shininess,enable_specular=enabled)
    def test_dark_specular_stays_dark_not_inverted_to_white(self):
        tint=parameters(self.material())['Specular Tint']
        self.assertLess(tint[0],.02)
        self.assertEqual(tint[:3],(linear(.149),)*3)
    def test_shininess_changes_width_not_reflection_strength(self):
        broad=parameters(self.material(shininess=10));tight=parameters(self.material(shininess=200))
        self.assertEqual(broad['Specular IOR Level'],tight['Specular IOR Level'])
        self.assertEqual(broad['Specular Tint'],tight['Specular Tint'])
        self.assertGreater(broad['Roughness'],tight['Roughness'])
    def test_source_disabled_and_colored_highlights_survive(self):
        self.assertEqual(parameters(self.material(enabled=False))['Specular IOR Level'],0)
        self.assertEqual(parameters(self.material(color=(0,0,0,1)))['Specular Tint'],(0,0,0,1))
        tint=parameters(self.material(color=(.67,.24,0,1)))['Specular Tint']
        self.assertGreater(tint[0],tint[1]);self.assertEqual(tint[2],0)
    def test_ggx_half_width_matches_source_attenuation(self):
        for n in [10,50,200,300]:
            k=n/2;c2=k/(k+1)
            roughness=parameters(self.material(shininess=n))['Roughness'];alpha2=roughness**4
            self.assertAlmostEqual(c2/(k+(1-k)*c2),.5)
            self.assertAlmostEqual(alpha2**2/(c2*(alpha2-1)+1)**2,.5)

if __name__=='__main__':unittest.main()
