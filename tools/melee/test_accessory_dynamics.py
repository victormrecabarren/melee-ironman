import math,unittest
from pathlib import Path
from accessory_dynamics import read_setup,active_prefix
DATA=Path('/private/tmp/melee-asset-test')

@unittest.skipUnless((DATA/'PlKp.dat').exists(),'requires local extracted game data')
class AccessoryDataTest(unittest.TestCase):
    def test_bowser_hair_uses_source_natural_angle_and_ten_degree_cone(self):
        data=(DATA/'PlKp.dat').read_bytes();setup=read_setup(data)
        self.assertEqual(len(setup['chains']),1)
        chain=setup['chains'][0]
        self.assertEqual((chain['bone'],chain['count']),(49,2))
        self.assertAlmostEqual(chain['params'][0][2],math.radians(-150),places=6)
        self.assertAlmostEqual(chain['params'][0][6],math.radians(10),places=6)
        self.assertEqual(setup['colliders'],[])
        for name in ['Wait1','Fall','Landing','AttackS4','DamageN3','DamageFlyN','DamageFlyRoll']:
            self.assertEqual(active_prefix(data,setup,name),[0],name)

    def test_dk_fall_and_attack_keep_the_animated_root_but_idle_uses_full_chain(self):
        data=(DATA/'PlDk.dat').read_bytes();setup=read_setup(data)
        self.assertEqual((setup['chains'][0]['bone'],setup['chains'][0]['count']),(66,6))
        self.assertEqual(active_prefix(data,setup,'Wait'),[0])
        for name in ['Fall','Landing','AttackS4S','DamageN3','DamageFlyN','DamageFlyRoll']:
            self.assertEqual(active_prefix(data,setup,name),[1],name)
        self.assertEqual(setup['colliders'],[{'bone':44,'offset':[0,3,3],'radius':4.5}])
        with self.assertRaisesRegex(ValueError,'Missing dynamics motion'):active_prefix(data,setup,'NotAnAnimation')

if __name__=='__main__':unittest.main()
