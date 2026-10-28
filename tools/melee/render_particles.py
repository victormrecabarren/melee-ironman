"""Render original EfCoData particle scripts/textures, not painted substitutes.

Bounded subset for common smash flash (11) and electric hit (12 + children).
Formats/commands: HSDRawViewer Particle/ParticleGenerator and ps.frag.
The random seed is fixed for reproducible atlases. Camera-facing billboards
use the original RGBA interpolation; full GX lighting is not emulated.
"""
import argparse
import json
import math
import random
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
from PIL import Image
from dat_assets import roots
from move_data import u32


class Bank:
    def __init__(self, path):
        self.data=path.read_bytes(); r=roots(self.data)['effCommonDataTable']
        self.bank=32+u32(self.data,r);self.texbank=32+u32(self.data,r+4);self.cache={}

    def generator(self, index):
        d=self.data;b=self.bank;p=b+u32(d,b+12+index*4);end=b+u32(d,b+16+index*4)
        flags,tex,life,plife,kind=struct.unpack_from('>HhhhI',d,p)
        gravity,friction,vx,vy,vz,radius,angle,rate,size,a,b,c=struct.unpack_from('>12f',d,p+12)
        shape=flags&15
        if shape not in [0,2,5,8]:raise ValueError(f'Unsupported generator {index} shape {shape}')
        if shape==0 and any([a,b,c]):raise ValueError('Unsupported non-default disc arc')
        if shape==5 and min(a,b,c)<0:raise ValueError('Unsupported rect edge flags')
        return SimpleNamespace(index=index,shape=shape,params=np.array([a,b,c]),tex=tex,life=life,plife=plife,kind=kind,gravity=gravity,friction=friction,
            velocity=np.array([vx,vy,vz]),radius=radius,angle=angle,rate=rate,size=size,commands=d[p+60:end])

    def texture(self, group, frame):
        key=(group,frame)
        if key not in self.cache:
            from shared.gx_texture import decode_texture
            d=self.data;b=self.texbank;p=b+u32(d,b+4+group*4)
            count,fmt,palfmt,w,h=struct.unpack_from('>5I',d,p)
            if not 0<=frame<count:raise ValueError(f'Texture frame outside group {group}: {frame}/{count}')
            image=b+u32(d,p+24+frame*4);palette=None
            if fmt in [8,9,10]:
                pal=b+u32(d,p+24+count*4+frame*4)
                palette=SimpleNamespace(raw_data=d[pal:],format=palfmt)
            pixels=decode_texture(d[image:],w,h,fmt,palette)
            self.cache[key]=np.array(pixels,dtype=np.uint8).reshape(h,w,4)[::-1].copy()
        return self.cache[key]


class Particle:
    def __init__(self, gen, pos, vel, rng, spawn):
        self.g=gen;self.pos=pos;self.previous=pos.copy();self.origin=pos.copy();self.trail=-1.;self.tornado=None;self.vel=vel;self.rng=rng;self.spawn=spawn
        self.life=gen.plife+1;self.size=gen.size;self.rotation=0.;self.rot_target=0.
        self.mirrorS=False;self.mirrorT=False;self.flip=[False,False];self.directional=False;self.pc=0;self.wait=1;self.pose=0;self.kind=gen.kind;self.loop=0;self.mark=0
        self.prim=np.array([255.]*4);self.env=np.zeros(4);self.targets={};self.code=gen.commands

    def byte(self):
        v=self.code[self.pc];self.pc+=1;return v

    def extended(self):
        v=self.byte();return ((v&127)<<8)|self.byte() if v&128 else v

    def float(self):
        v=struct.unpack_from('>f',self.code,self.pc)[0];self.pc+=4;return v

    def target(self, name, value, count):
        self.targets.pop(name,None)
        if count:self.targets[name]=[value,count]
        else:setattr(self,name,value)

    def update(self):
        for name,(value,count) in list(self.targets.items()):
            old=getattr(self,name);setattr(self,name,old+(value-old)/count)
            if count==1:del self.targets[name]
            else:self.targets[name][1]-=1
        self.wait-=1
        if self.wait==0:
            for _ in range(512):
                cmd=self.byte()
                if cmd<0x80:
                    self.wait=cmd&31
                    if cmd&32:self.wait=self.wait*256+self.byte()
                    if cmd&0xc0==0x40:self.pose=self.byte();self.kind|=1024
                elif 0x80<=cmd<=0x9f:
                    target=self.pos if cmd<0x90 else self.vel
                    for axis in range(3):
                        if cmd&(1<<axis):
                            value=self.float()
                            target[axis]=target[axis]+value if cmd&8 else value
                elif cmd&0xf0 in [0xc0,0xd0]:
                    name='prim' if cmd&0xf0==0xc0 else 'env';count=self.extended()
                    color=getattr(self,name).copy()
                    for i in range(4):
                        if cmd&(1<<i):color[i]=self.byte()
                    self.target(name,color,count)
                elif cmd in [0xa0,0xac]:
                    count=self.extended();size=self.float()
                    if cmd==0xac:size+=self.float()*self.rng.random()
                    self.target('size',size,count)
                elif cmd in [0xba,0xbb]:
                    name='prim' if cmd==0xba else 'env'
                    value=self.targets[name][0].copy() if name in self.targets else getattr(self,name).copy()
                    for i in range(4):
                        byte=self.byte();delta=byte if byte<128 else byte-256
                        value[i]=int(np.clip(value[i]+2*delta*self.rng.random(),0,255))
                    self.target(name,value,self.targets[name][1] if name in self.targets else 0)
                elif cmd==0xe0:
                    changes=[]
                    for _ in range(4):
                        byte=self.byte();changes.append(2*(byte if byte<128 else byte-256)*self.rng.random())
                    for name in ['prim','env']:
                        value=self.targets[name][0].copy() if name in self.targets else getattr(self,name).copy()
                        self.target(name,np.clip(value+changes,0,255).astype(int),self.targets[name][1] if name in self.targets else 0)
                elif cmd==0xad:self.kind|=128
                elif cmd==0xa5:
                    index=(self.byte()<<8)|self.byte();self.spawn(index,self.pos.copy())
                elif cmd==0xef:
                    index=(self.byte()<<8)|self.byte();flag=self.byte()
                    # Link group bits do not change these rendered billboards.
                    self.spawn(index,self.pos.copy())
                elif cmd in [0xe4,0xe5]:
                    axis=cmd-0xe4;mode=self.byte()&3
                    self.flip[axis]=bool(mode) if mode<2 else (not self.flip[axis] if mode==2 else self.rng.random()>=.5)
                elif cmd==0xae:self.mirrorS=self.mirrorT=False
                elif cmd==0xaf:self.mirrorS=True;self.mirrorT=False
                elif cmd==0xb0:self.mirrorS=False;self.mirrorT=True
                elif cmd==0xb1:self.mirrorS=self.mirrorT=True
                elif cmd==0xe8:self.trail=self.float()
                elif cmd==0xe6:self.directional=True
                elif cmd==0xe7:self.directional=False
                elif cmd==0xa8:
                    for i in range(3):self.pos[i]+=self.float()*(2*self.rng.random()-1)
                elif cmd==0xbe:
                    for i in range(3):self.vel[i]*=self.float()
                elif cmd==0xa9:
                    angle=self.float()
                    speed=np.linalg.norm(self.vel)
                    if speed:
                        az=math.atan2(self.vel[1],self.vel[2]);el=math.atan2(self.vel[0],math.hypot(self.vel[1],self.vel[2]))
                        phi=math.tau*self.rng.random();ca=math.cos(az);sa=math.sin(az);ce=math.cos(el);se=math.sin(el)
                        x=speed*math.sin(angle)*math.cos(phi);y=speed*math.sin(angle)*math.sin(phi);z=speed*math.cos(angle)
                        self.vel=np.array([x*ce+z*se,ce*z*sa-se*x*sa+y*ca,ce*z*ca-se*x*ca-y*sa])
                elif cmd==0xab:self.vel*=self.float()
                elif cmd==0xbc:self.pose=int(self.byte()+self.byte()*self.rng.random());self.kind|=1024
                elif cmd==0xbd:
                    speed=self.float()+self.float()*self.rng.random();norm=np.linalg.norm(self.vel)
                    if norm:self.vel=self.vel/norm*speed
                elif cmd==0xb6:
                    count=self.extended();self.rot_target+=self.float();self.target('rotation',self.rot_target,count)
                elif cmd==0xed:
                    base=self.float();span=self.float();step=self.byte();r=self.rng.random()
                    value=base+span*(r if not step else ((step+1)*r)/step)
                    self.rotation+=value;self.rot_target+=value
                elif cmd==0xfa:self.loop=self.byte();self.mark=self.pc
                elif cmd==0xfb:
                    self.loop-=1
                    if self.loop:self.pc=self.mark
                elif cmd in [0xfe,0xff]:self.life=1;break
                else:raise ValueError(f'Unsupported particle opcode {cmd:#x} in generator {self.g.index}')
                if self.wait:break
            else:raise ValueError('Unbounded particle script')
        self.life-=1
        if self.life:
            self.previous=self.pos.copy()
            if self.tornado is not None:
                angle,radial,height,basis,speed=self.tornado
                height+=speed;angle+=self.g.gravity
                radius=(abs(self.g.radius)+height*math.tan(abs(self.g.angle)))*radial
                self.pos=self.origin+basis@np.array([radius*math.cos(angle),radius*math.sin(angle),height])
                self.tornado=[angle,radial,height,basis,speed]
            else:
                if self.kind&1:self.vel[1]-=self.g.gravity
                if self.kind&2:self.vel*=self.g.friction
                self.pos+=self.vel

    def image(self, bank, units):
        if not self.kind&1024 or self.size<=0:return None
        tex=bank.texture(self.g.tex,self.pose).astype(float)/255
        if self.mirrorS:tex=np.concatenate([tex,tex[:,::-1]],axis=1)
        if self.mirrorT:tex=np.concatenate([tex[::-1],tex],axis=0)
        if self.flip[0]:tex=tex[:,::-1]
        if self.flip[1]:tex=tex[::-1]
        rgba=(self.env+(self.prim-self.env)*tex) if self.kind&128 else tex*self.prim
        pixels=np.clip(rgba,0,255).astype(np.uint8)
        size=max(1,round(2*self.size*units))
        im=Image.fromarray(pixels).resize((size,size),Image.Resampling.BILINEAR)
        angle=self.rotation-(math.atan2(self.vel[0],self.vel[1]) if self.directional else 0)
        if self.trail>=0:
            # psdisp.c: two corners at the previous position and two at
            # the current position. This affine quad preserves source texture.
            c,s=math.cos(self.rotation),math.sin(self.rotation)
            right=self.size*np.array([c-s,s+c]);up=self.size*np.array([-c-s,c-s])
            delta=self.previous[:2]-self.pos[:2]
            points=np.array([delta-right,-up,right,delta+up])*np.array([units,-units])
            low=np.floor(points.min(axis=0));high=np.ceil(points.max(axis=0));dims=np.maximum(1,high-low).astype(int)
            # Texture corners: top-left, bottom-left, bottom-right, top-right.
            basis=np.column_stack([points[3]-points[0],points[1]-points[0]])
            if abs(np.linalg.det(basis))>1e-8:
                inv=np.diag([im.width,im.height])@np.linalg.inv(basis)
                offset=inv@(low-points[0]);coeff=tuple(np.column_stack([inv,offset]).flat)
                im=im.transform(tuple(dims),Image.Transform.AFFINE,coeff,Image.Resampling.BILINEAR)
                return im,low
        if angle:im=im.rotate(math.degrees(angle),resample=Image.Resampling.BICUBIC,expand=True)
        return im,np.array([-im.width/2,-im.height/2])


def render(bank, index, frames, seed=41, size=384, units=5, origin=None):
    rng=random.Random(seed);generators=[];particles=[];origin=origin or [size/2,size/2]
    def spawn(index,pos):generators.append([bank.generator(index),pos,0,0.])
    for root in (index if isinstance(index,(list,tuple)) else [index]):spawn(root,np.zeros(3))
    images=[]
    for frame in range(frames):
        # Children created by a root script are eligible this same tick.
        gi=0
        while gi<len(generators):
            gen,pos,age,acc=generators[gi]
            if age<gen.life:
                acc+=(-gen.rate if gen.rate<0 else gen.rate*rng.random())
                tornado_start=rng.random()*math.tau if gen.shape==2 else 0
                for emitted in range(int(acc)):
                    rad=(1 if gen.radius<0 else rng.random());theta=rng.random()*math.tau
                    offset=np.array([rad*abs(gen.radius)*math.cos(theta),rad*abs(gen.radius)*math.sin(theta),0.])
                    speed=np.linalg.norm(gen.velocity);angle=rad*abs(gen.angle)
                    vel=speed*np.array([math.sin(angle)*math.cos(theta),math.sin(angle)*math.sin(theta),math.cos(angle)])
                    if gen.shape==8:
                        # generator.c sphere emission: latitude range selects
                        # the polar cone; velocity follows its sampled radial
                        # direction. A negative range reverses radial velocity.
                        latitude=abs(gen.params[0])
                        polar=math.sqrt(rng.random())*(math.pi/2 if latitude==0 or abs(latitude-math.pi)<.001 else latitude)
                        if (latitude==0 or abs(latitude-math.pi)<.001) and rng.random()<.5:polar=math.pi-polar
                        azimuth=rng.random()*math.tau
                        radius=abs(gen.radius)*(1 if gen.radius<0 else math.sqrt(rng.random()))
                        direction=np.array([math.sin(polar)*math.cos(azimuth),math.sin(polar)*math.sin(azimuth),math.cos(polar)])
                        radial_speed=speed*(-1 if gen.params[0]<0 else 1)
                        if gen.radius>=0 and radial_speed<0:radial_speed*=radius/gen.radius if gen.radius else 0
                        offset=radius*direction;vel=radial_speed*direction
                    if gen.shape==5:
                        offset=gen.params*np.array([rng.random()-.5 for _ in range(3)])
                        vel=np.array([0.,0.,speed])
                    # Rotate local disc normal onto the descriptor's velocity.
                    basis=np.eye(3)
                    if speed:
                        z=gen.velocity/speed;helper=np.array([0.,1.,0.]) if abs(z[1])<.99 else np.array([1.,0.,0.])
                        x=np.cross(helper,z);x/=np.linalg.norm(x);y=np.cross(z,x);basis=np.column_stack([x,y,z])
                        offset=basis@offset;vel=basis@vel
                    if gen.shape==2:offset=np.zeros(3)
                    particle=Particle(gen,pos+offset,vel,rng,spawn)
                    if gen.shape==2:
                        angle=tornado_start+(emitted+1)*math.tau/int(acc) if gen.angle<0 else rng.random()*math.tau
                        particle.tornado=[angle,1 if gen.radius<0 else rng.random(),0,basis,speed]
                    particle.update()
                    if particle.life:particles.append(particle)
                acc-=int(acc)
            generators[gi][2:]=[age+1,acc];gi+=1
        image=Image.new('RGBA',(size,size))
        for p in particles:
            im=p.image(bank,units)
            if im:
                im,offset=im
                xy=(round(origin[0]+p.pos[0]*units+offset[0]),round(origin[1]-p.pos[1]*units+offset[1]))
                image.alpha_composite(im,xy)
        images.append(image)
        for p in particles:p.update()
        particles=[p for p in particles if p.life>0]
    return images


def run(args):
    sys.path.insert(0,str(args.importer.resolve()));bank=Bank(args.data/'EfCoData.dat')
    manifest_path=args.output/'manifest.json';manifest=json.loads(manifest_path.read_text())
    specs=[('normal-impact',[2,306,307],24),('smash-flash',11,6),('electric',12,24),('hand-electric',19,20),('hand-fire',75,30),('fire-impact',20,40),('body-fire',55,40),('body-dark',225,40),('dark-impact',406,40),('hammer-dust',60,30),('charge-dust',263,30),('taunt-step-dust',90,40),('taunt-sparkle',93,40),('ko-particles',212,60)]
    for name,index,frames in specs:
        if args.only and name not in args.only:continue
        size,units,origin=(1024,.64,[512,900]) if name=='ko-particles' else (384,5,[192,192])
        if name=='normal-impact':size,origin=1024,[512,512]
        images=render(bank,index,frames,size=size,units=units,origin=origin);columns=min(8,frames)
        atlas=Image.new('RGBA',(size*columns,size*math.ceil(frames/columns)))
        for i,im in enumerate(images):atlas.paste(im,((i%columns)*size,(i//columns)*size))
        filename=name+('-particles-v1' if name=='normal-impact' else '')+'.webp'
        atlas.save(args.output/filename,lossless=True,method=6)
        manifest['environment'][name]={'file':filename,'width':size,'height':size,'columns':columns,
            'frames':frames,'fps':60,'anchor':origin,'pixelsPerGameUnit':units,
            'source':f'EfCoData.dat: generator {index}, original texture bank and command stream','seed':41}
        if name=='normal-impact':
            manifest['environment'][name]['source']='EfCoData.dat model 10: HSD_A_J_PTCL 0x80 / 0x4C80 / 0x4CC0 → generators 2 / 306 / 307'
            manifest['environment'][name]['damageScale']={'base':.3,'multiplier':.04,'minimum':.3,'maximum':1.5}
    if 'hand-fire' in manifest['environment']:manifest.setdefault('effectMap',{})['1041']='hand-fire'
    manifest_path.write_text(json.dumps(manifest,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['data','output','importer']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--only',nargs='+')
    run(p.parse_args())
