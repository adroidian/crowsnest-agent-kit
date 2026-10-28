"""Execute the actual inline deck JS with a minimal DOM; no network or browser deps."""
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_all_districts_select_their_own_project_and_only_ep6_has_replay():
    assert shutil.which("node"), "Node.js is required for deck navigation regression tests"
    script = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const data = JSON.parse(fs.readFileSync('deck/sim_dataset.json'));
const replay = JSON.parse(fs.readFileSync('deck/replay_ep6.json'));
const elements = new Map();
const created = [];
function element() {
  return {style:{}, dataset:{}, attributes:{}, className:'', textContent:'', children:[], clientWidth:1152, clientHeight:648,
    classList:{toggle(){}}, appendChild(x){this.children.push(x)},
    replaceChildren(){this.children=[]},
    setAttribute(k,v){this.attributes[k]=v}, getAttribute(k){return this.attributes[k]},
    querySelector(){return elements.get('heading')}, remove(){this.removed=true}};
}
for (const id of ['plate','mode','counters','card','detail','fill','stage','heading',
  'motion-layer','scene-caption','pause','previous','next','restart','motion-status'])
  elements.set(id, element());
const nav = ['world','project','nest'].map(v=>Object.assign(element(),{dataset:{v}}));
const listeners = {}, media = {matches:false,addEventListener(name,fn){this.change=fn}};
const frames = new Map(); let nextFrame=0;
const context = vm.createContext({console, URLSearchParams,
  window:{matchMedia:()=>media,location:{search:''},addEventListener(){}},
  Image:function(){},
  document:{hidden:false,addEventListener:(name,fn)=>{listeners[name]=fn},getElementById:id=>elements.get(id),
    createElement:()=>{const e=element();created.push(e);return e},
    querySelectorAll:s=>s==='nav button'?nav:created.filter(e=>!e.removed&&['hot','nestdot'].includes(e.className))},
  fetch:async name=>({ok:true,json:async()=>name==='sim_dataset.json'?data:replay}),
  requestAnimationFrame:fn=>{const id=++nextFrame;frames.set(id,fn);return id},
  cancelAnimationFrame:id=>frames.delete(id)});
const html=fs.readFileSync('deck/index.html','utf8');
vm.runInContext(fs.readFileSync('deck/motion.js','utf8'),context);
vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
(async()=>{
  await new Promise(resolve=>setImmediate(resolve));
  const get=id=>elements.get(id).textContent;
  const real=data.projects.find(p=>p.contains_real_nest);
  for(const project of data.projects){
    vm.runInContext("setView('world')", context);
    const button=created.find(e=>!e.removed&&e.className==='hot'&&
      e.textContent.startsWith(project.name.split('—')[0].trim()+' ·'));
    assert.ok(button, 'missing district '+project.id);
    button.onclick();
    assert.equal(get('heading'),'Project — '+project.name);
    const agents=data.agents.filter(a=>a.project_id===project.id);
    assert.ok(get('counters').startsWith(project.name+': '+agents.length+' agents'));
    assert.equal(get('mode'),'SIMULATED');
    assert.ok(context.window.DeckMotion.getState().routes.every(r=>r.projectId===project.id),
      'motion must use selected-project rows');
    assert.equal(frames.size,1,'view changes retain exactly one animation clock');
    const nests=created.filter(e=>!e.removed&&e.className==='nestdot');
    assert.equal(nests.length,8);
    const playable=nests.filter(e=>typeof e.onclick==='function');
    assert.equal(playable.length,project.contains_real_nest?1:0, project.id);
    if(project.contains_real_nest){
      playable[0].onclick();
      assert.equal(get('mode'),'REPLAY — RECORDED');
      assert.ok(get('counters').includes(replay.gig));
      nav.find(n=>n.dataset.v==='project').onclick();
      assert.equal(get('heading'),'Project — '+project.name);
    }else{
      assert.ok(get('detail').includes('No recorded work'));
      vm.runInContext("setView('nest')",context);
      assert.equal(get('mode'),'SIMULATED','non-EP6 cannot enter replay implicitly');
      assert.equal(get('heading'),'Project — '+project.name);
    }
  }
  nav.find(n=>n.dataset.v==='nest').onclick();
  assert.equal(get('mode'),'REPLAY — RECORDED');
  nav.find(n=>n.dataset.v==='project').onclick();
  assert.equal(get('heading'),'Project — '+real.name);
  assert.throws(()=>vm.runInContext("setView('project','missing-project')",context),
    /Unknown project/);
  const api=context.window.DeckMotion;
  api.setView('nest',real.id);
  api.pause(); assert.equal(frames.size,0);
  const frozen=JSON.stringify(api.getState().routes);
  api.setStage(1);api.seek(.3);
  assert.notEqual(JSON.stringify(api.getState().routes),frozen,'seek updates real sprite poses while paused');
  assert.equal(api.getState().stageKey,'refusal_local');
  assert.equal(api.getState().paused,true);
  elements.get('next').onclick();assert.equal(api.getState().stageKey,'refusal_http');
  elements.get('previous').onclick();assert.equal(api.getState().stageKey,'refusal_local');
  elements.get('restart').onclick();assert.equal(api.getState().stageKey,'posted');
  api.resume();assert.equal(frames.size,1);
  function frameAt(ms){const [id,fn]=frames.entries().next().value;frames.delete(id);fn(ms)}
  frameAt(0);frameAt(4100);assert.equal(api.getState().stageKey,'refusal_local');
  api.pause();assert.equal(frames.size,0);
  const held=JSON.stringify(api.getState());assert.equal(JSON.stringify(api.getState()),held);
  api.resume();context.document.hidden=true;listeners.visibilitychange();assert.equal(frames.size,0);
  assert.equal(api.getState().hidden,true);
  context.document.hidden=false;listeners.visibilitychange();assert.equal(frames.size,1);
  media.change({matches:true});assert.equal(frames.size,0);
  assert.equal(api.getState().reducedMotion,true);api.setStage(5);
  const staticPose=JSON.stringify(api.getState().routes);api.seek(.9);
  assert.equal(JSON.stringify(api.getState().routes),staticPose,'reduced motion keeps meaningful static poses');
  assert.equal(elements.get('pause').disabled,true);
  media.change({matches:false});api.pause();
  for(let i=0;i<30;i++){api.setView('world');api.setView('project',real.id);api.setView('nest')}
  assert.equal(frames.size,0,'paused navigation must not create loops');
  assert.equal(elements.get('motion-layer').children.length,6,'three labels + two actor crows + one focal signal');
  api.setStage(6);
  const reviewSignal=api.getState().routes.find(r=>r.kind==='review');
  assert.equal(reviewSignal.moving,false,'buyer reviews at own nest, no independent reviewer');
  assert.ok(!api.getState().routes.some(r=>r.id==='roost-escrow'||r.id==='roost-reviewer'));
  api.resume();assert.equal(frames.size,1);
  console.log('PASS: all 9 districts, scoped counters and sprite rows, replay boundary, navigation memory, unknown ID; actual DOM motion seek, controls, progression, hidden/reduced, loop cleanup');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
