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
  return {style:{}, dataset:{}, className:'', textContent:'', children:[],
    classList:{toggle(){}}, appendChild(x){this.children.push(x)},
    querySelector(){return elements.get('heading')}, remove(){this.removed=true}};
}
for (const id of ['plate','mode','counters','card','detail','fill','stage','heading'])
  elements.set(id, element());
const nav = ['world','project','nest'].map(v=>Object.assign(element(),{dataset:{v}}));
const context = vm.createContext({console,
  document:{getElementById:id=>elements.get(id),
    createElement:()=>{const e=element();created.push(e);return e},
    querySelectorAll:s=>s==='nav button'?nav:created.filter(e=>!e.removed)},
  fetch:async name=>({json:async()=>name==='sim_dataset.json'?data:replay}),
  setInterval:()=>1, clearInterval:()=>{}});
const html=fs.readFileSync('deck/index.html','utf8');
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
  console.log('PASS: all 9 districts, scoped counters, replay boundary, navigation memory, unknown ID');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run(["node", "-e", script], cwd=ROOT, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
