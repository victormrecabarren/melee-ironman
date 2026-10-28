import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

function fallback(){
  const html=readFileSync(new URL('../index.html',import.meta.url),'utf8');
  const listeners={},nodes=[],timers=new Map();let id=0;
  const document={getElementById:target=>nodes.find(n=>n.id===target),
    createElement:tag=>({tag,style:{},setAttribute(){},append(){},remove(){nodes.splice(nodes.indexOf(this),1);}}),
    body:{append:node=>nodes.push(node)}};
  vm.runInNewContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],{
    document,window:{addEventListener:(name,fn)=>{listeners[name]=fn;}},location:{reload(){}},
    setTimeout:fn=>{timers.set(++id,fn);return id;},clearTimeout:id=>timers.delete(id)});
  return {nodes,event:(name,data={})=>listeners[name](data),flush:()=>{for(const [id,fn] of [...timers]){timers.delete(id);fn();}}};
}
test('normal startup and navigation never display the error fallback',()=>{
  const f=fallback();assert.equal(f.nodes.length,0);
  f.event('error',{message:'Temporary startup failure'});assert.equal(f.nodes.length,0);
  f.event('ironman:ready');f.flush();assert.equal(f.nodes.length,0);
  f.event('error',{message:'Request interrupted'});f.event('pagehide');f.flush();assert.equal(f.nodes.length,0);
  f.event('pageshow');f.event('unhandledrejection',{reason:{name:'AbortError'}});f.flush();assert.equal(f.nodes.length,0);
});
test('persistent failures still show a reload fallback and successful recovery removes it',()=>{
  const f=fallback();f.event('error',{message:'Module failed'});f.flush();
  assert.equal(f.nodes[0].id,'startup-error');f.event('ironman:ready');assert.equal(f.nodes.length,0);
});
