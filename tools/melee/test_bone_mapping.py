import struct,unittest
from dat_assets import fighter_bone_index

class SparseFighterBones(unittest.TestCase):
    def test_reserved_attachment_slots_do_not_shift_damage_bones(self):
        data=bytearray(512)
        struct.pack_into('>5I',data,0,512,400,0,1,0)
        struct.pack_into('>II',data,432,32,0)
        name=b'ftLoadCommonData\0';data[440:440+len(name)]=name
        struct.pack_into('>I',data,64+0x14,128) # table at160
        struct.pack_into('>I',data,160+4*4,168) # Kirby descriptor at200
        struct.pack_into('>II',data,200,188,3)
        data[220]=2;data[224]=5;data[228]=7
        self.assertEqual(fighter_bone_index(data,4,1),1)
        self.assertEqual(fighter_bone_index(data,4,6),4)
        self.assertEqual(fighter_bone_index(data,4,9),6)
        self.assertEqual(fighter_bone_index(data,0,9),9)
        with self.assertRaisesRegex(ValueError,'attached model'):fighter_bone_index(data,4,5)
if __name__=='__main__':unittest.main()
