import test from 'node:test';
import assert from 'node:assert/strict';
import {spriteFrame,clipFiles} from './spriteAtlas.js';
test('packed frames retain logical offsets and choose the correct page',()=>{
 const clip={pages:[{file:'a.webp'},{file:'b.webp'}],rects:[[1,20,30,40,50,120,210]]};
 assert.deepEqual(clipFiles(clip),['a.webp','b.webp']);
 assert.deepEqual(spriteFrame(clip,0,{}),{file:'b.webp',x:20,y:30,width:40,height:50,dx:120,dy:210});
});
test('unpacked exports remain compatible during regeneration',()=>{
 assert.deepEqual(spriteFrame({file:'old.webp'},9,{columns:8,width:512,height:384}),{file:'old.webp',x:512,y:384,width:512,height:384,dx:0,dy:0});
});
