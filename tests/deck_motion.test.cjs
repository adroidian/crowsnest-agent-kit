// Real motion/state implementation; no browser or fabricated service events.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const {Clock, simulatedRoutes, pose, replayRoutes} = require('../deck/motion.js');
const data = JSON.parse(fs.readFileSync('deck/sim_dataset.json'));
const replay = JSON.parse(fs.readFileSync('deck/replay_ep6.json'));
const before = JSON.stringify(data);
for (const project of data.projects) {
  const routes = simulatedRoutes(data, 'project', project.id);
  assert.ok(routes.length >= 4 && routes.length <= 8);
  assert.deepEqual(routes, simulatedRoutes(data, 'project', project.id));
  for (const route of routes) {
    const agent = data.agents.find(a => a.id === route.id);
    assert.equal(agent.project_id, project.id);
    assert.equal(route.moving, agent.state === 'in_flight');
    if (route.moving) assert.notDeepEqual(pose(route, .2), pose(route, .6));
    else assert.deepEqual(pose(route, .2), pose(route, .6));
  }
}
assert.equal(JSON.stringify(data), before, 'motion must not mutate counters/data');
assert.ok(simulatedRoutes(data, 'world').length <= 8);
const c = new Clock(replay.stages);
c.advance(1000); assert.equal(c.snapshot().elapsed, 1000);
c.pause(); c.advance(2000); assert.equal(c.snapshot().elapsed, 1000);
c.resume(); c.advance(3000); assert.equal(c.snapshot().stageKey, 'refusal_local');
c.setStage(2); c.setProgress(.5); assert.equal(c.snapshot().progress, .5);
c.setHidden(true); c.advance(9999); assert.equal(c.snapshot().progress, .5);
c.setHidden(false); c.advance(3000); assert.equal(c.snapshot().stageKey, 'proposed');
c.restart(); assert.equal(c.snapshot().stageKey, 'posted'); assert.equal(c.snapshot().progress, 0);
c.pause(); c.setStage(4); assert.equal(c.snapshot().paused, true);
c.resume(); c.advance(1000000); assert.equal(c.snapshot().stageKey, 'settled');
assert.equal(c.snapshot().paused, true); assert.equal(c.snapshot().progress, 1);
assert.throws(() => c.setStage(-1), RangeError); assert.throws(() => c.setStage(1.5), RangeError);
c.setReduced(true); c.restart(); c.resume(); c.advance(10000);
assert.equal(c.snapshot().elapsed, 0); assert.equal(c.snapshot().running, false);
c.setStage(3); assert.equal(c.snapshot().stageKey, 'proposed');
const local = replayRoutes('refusal_local').find(r => r.role === 'courier');
const http = replayRoutes('refusal_http').find(r => r.role === 'courier');
const proposal = replayRoutes('proposed').find(r => r.role === 'courier');
const delivered = replayRoutes('delivered').find(r => r.role === 'courier');
assert.deepEqual(pose(local, 1).point, local.from, 'local refusal returns before reaching buyer');
assert.deepEqual(pose(http, 1).point, http.from, 'HTTP refusal returns; never delivered');
assert.notDeepEqual(pose(local, .5).point, pose(http, .5).point);
assert.deepEqual(pose(proposal, 1).point, proposal.to);
assert.equal(delivered.carry, true);
assert.equal(replay.stages.reduce((sum, s) => sum + s.duration_ms, 0), 50000);
console.log('PASS: deterministic scoped routes; immutable simulation; pause/hidden/reduced; progression/restart; distinct refusal/proposal/delivery paths; 50s timeline');
