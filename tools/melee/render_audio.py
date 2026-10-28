"""Resolve original SEM sound IDs and decode SSM Nintendo DSP ADPCM to WAV.

Layouts verified against HSDLib SEM/SSM/DSP readers. Exports only the preview
move's swing, one source voice, hit sound, and left/right blast-zone sounds.
"""
import argparse
import json
import struct
import wave
from pathlib import Path


def decode_adpcm(data, coefficients, history1=0, history2=0):
    samples=[]
    for offset in range(0, len(data)-7, 8):
        header=data[offset]; predictor=header>>4; scale=1<<(header&15)
        if predictor>=8: raise ValueError('Invalid DSP predictor')
        c1,c2=coefficients[predictor*2:predictor*2+2]
        for byte in data[offset+1:offset+8]:
            for nibble in (byte>>4,byte&15):
                signed=nibble if nibble<8 else nibble-16
                sample=((signed*scale<<11)+c1*history1+c2*history2+1024)>>11
                sample=max(-32768,min(32767,sample))
                samples.append(sample);history2,history1=history1,sample
    return samples


def read_bank(path):
    data=path.read_bytes();header,_,count,start=struct.unpack_from('>4I',data)
    pos=16; sounds={}
    for index in range(count):
        channels,rate=struct.unpack_from('>2I',data,pos);pos+=8
        if channels not in (1,2) or not 8000<=rate<=96000:raise ValueError('Invalid SSM header')
        decoded=[]
        for _ in range(channels):
            _,fmt,loop,end,current=struct.unpack_from('>2H3I',data,pos)
            if fmt!=0:raise ValueError('Only DSP ADPCM is supported')
            coef=struct.unpack_from('>16h',data,pos+16)
            h1,h2=struct.unpack_from('>2h',data,pos+52)
            begin=header+16+(current+1)//2-1;length=(end-current+1)//2+1
            decoded.append(decode_adpcm(data[begin:begin+length],coef,h1,h2));pos+=64
        sounds[start+index]=(rate,decoded)
    return sounds


def sem_commands(data, sound_id):
    u=lambda p:struct.unpack_from('>I',data,p)[0]
    count=u(8);bank,index=divmod(sound_id,10000)
    if bank>=count:raise ValueError('Unknown SEM bank')
    start,stop=u(12+bank*4),u(16+bank*4)
    if index>=stop-start:raise ValueError('Unknown SEM sound')
    table=12+(count+1)*4;entry=start+index
    begin,end=u(table+entry*4),u(table+(entry+1)*4)
    return [(data[p],int.from_bytes(data[p+2:p+4],'big')) for p in range(begin,end,4)]


def resolve_sem(data, sound_id, allow_static_pitch=False):
    commands=sem_commands(data,sound_id)
    if not allow_static_pitch and any(op==12 and value!=0 for op,value in commands):raise ValueError('Pitch-shifted SEM script requires pitch rendering')
    return next(value for op,value in commands if op==1)


def run(data_dir, output):
    banks={}
    for name in ['main','emblem','drmario']:banks.update(read_bank(data_dir/(name+'.ssm')))
    sem=(data_dir/'smash2.sem').read_bytes()
    ids={'roy-swing':158,'roy-hit':113,'roy-voice':310006,
         'dr-mario-swing':155,'dr-mario-hit':103,'dr-mario-voice':90039,
         'ko-left':136,'ko-right':137,'dr-mario-land':389,'roy-land':515}
    result={}
    for key,sound_id in ids.items():
        sample_id=resolve_sem(sem,sound_id);rate,channels=banks[sample_id]
        size=min(map(len,channels));values=[channels[ch][i] for i in range(size) for ch in range(len(channels))]
        filename=key+'.wav'
        with wave.open(str(output/filename),'wb') as w:
            w.setnchannels(len(channels));w.setsampwidth(2);w.setframerate(rate)
            w.writeframes(struct.pack('<'+'h'*len(values),*values))
        result[key]={'file':filename,'soundId':sound_id,'sampleId':sample_id,'duration':size/rate}
    p=output/'manifest.json';manifest=json.loads(p.read_text());manifest['audio']=result
    p.write_text(json.dumps(manifest,indent=2)+'\n')
    print('Exported',len(result),'original sounds')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();run(args.data,args.output)
