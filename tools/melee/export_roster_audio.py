"""Export source move, landing and impact sounds for every roster character.

Impact lookup: doldecomp/melee src/melee/lb/lbcollision.c lbColl_803B9880.
Uses fixed first smash-voice choice for reproducible review, original SEM IDs.
Unsupported pitch scripts remain in the report rather than being substituted.
"""
import argparse,json,struct,wave
from pathlib import Path
from dat_assets import roots,animations
from move_data import decode_script,u32,read_action
from smash_sequence import read_preview_move
from render_audio import read_bank,resolve_sem,sem_commands
HIT_SOUNDS=[0x83D60]*3+[91,90,89,88,87,86,111,112,113,84,84,84,90,89,223,225,225,225,98,99,100,101,102,103]+[0x4461B]*3+[241]*3+[94,93,92,0x35BAF,0x35BB2,0x35BB5,0x83D60,0x83D60,525]
BANKS='main captain clink dk drmario emblem falco fox ganon gw ice kirby koopa link luigi mario mars mewtwo ness peach pichu pikachu purin samus yoshi zs'.split()
def run(args):
    roster=json.loads(Path(__file__).with_name('roster.json').read_text());requests={'sound-123':123};report={}
    sem=(args.data/'smash2.sem').read_bytes()
    for f in roster:
        code,slug=f['code'],f['slug'];path=args.data/f'Pl{code}.dat'
        names=[n for n,_,_ in animations(args.data/f'Pl{code}AJ.dat')]
        move=read_preview_move(path,next(n for n in ['AttackS4S','AttackS4','AttackS41'] if n in names))
        for event in move['events']:
            if event['opcode']==17:requests['sound-'+str(event['fields']['SFX ID'])]=event['fields']['SFX ID']
        for action in [n for n in names if n in ('Appeal','AppealL','AppealR')]:
            for event in read_action(path,action)['events']:
                sound=event['fields'].get('SFX ID') if event['opcode']==17 else event['fields'].get('SFX ID 1') if event['name']=='Pseudo Random Sound Effect' else None
                if sound is not None:requests['sound-'+str(sound)]=sound
        if move['voices']:requests[slug+'-voice']=move['voices'][0]
        for hit in move['hitboxes']:
            sound=HIT_SOUNDS[hit['Hit SFX Kind']*3+hit['Hit SFX Severity']];requests['sound-'+str(sound)]=sound
        d=path.read_bytes();root=next(iter(roots(d).values()));table=32+u32(d,root+12)
        for i in range(341):
            p=32+u32(d,table+i*24)
            if not 32<=p<len(d):continue
            end=d.find(b'\0',p,min(len(d),p+256))
            if not d[p:end].endswith(b'_ACTION_Landing_figatree'):continue
            events=decode_script(d,32+u32(d,table+i*24+12))
            sounds=[e['fields']['Sound ID'] for e in events if e['opcode']==55]
            if sounds:requests[slug+'-land']=sounds[0];break
    wanted={}
    for key,sound in requests.items():
        try:wanted[key]=(sound,resolve_sem(sem,sound,allow_static_pitch=sound in (159,160)))
        except (ValueError,StopIteration) as e:report[key]=str(e)
    output={};remaining=set(wanted)
    for name in BANKS:
        bank=read_bank(args.data/(name+'.ssm'))
        for key in sorted(remaining.copy()):
            sound,sample=wanted[key]
            if sample not in bank:continue
            rate,channels=bank[sample];size=min(map(len,channels));filename=key+'.wav'
            values=[channels[ch][i] for i in range(size) for ch in range(len(channels))]
            with wave.open(str(args.output/filename),'wb') as w:
                w.setnchannels(len(channels));w.setsampwidth(2);w.setframerate(rate);w.writeframes(struct.pack('<'+'h'*len(values),*values))
            output[key]={'file':filename,'soundId':sound,'sampleId':sample,'duration':size/rate,'source':name+'.ssm'}
            if sound in (159,160):
                pitch=next(value for op,value in sem_commands(sem,sound) if op==12)
                pitch=pitch-65536 if pitch>32767 else pitch
                output[key].update(pitchCents=pitch,playbackRate=2**(pitch/1200),pitchSource='smash2.sem opcode 12 / AXDriverExec')
            remaining.remove(key)
        print(name,'remaining',len(remaining),flush=True)
    report.update({k:'Sample bank missing' for k in remaining})
    path=args.output/'manifest.json';m=json.loads(path.read_text());m['audio'].update(output);m['common']['hitSoundIds']=HIT_SOUNDS;m['audioReview']=report
    temp=path.with_suffix('.audio.tmp');temp.write_text(json.dumps(m,indent=2)+'\n');temp.replace(path)
    print('EXPORTED',len(output),'REVIEW',report,flush=True)
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['data','output']:p.add_argument('--'+n,type=Path,required=True)
    run(p.parse_args())
