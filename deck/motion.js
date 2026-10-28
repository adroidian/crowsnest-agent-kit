/* One clock owns courier motion and replay state. No writes, randomness or live events. */
(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.DeckMotionCore = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const POS = [[22,30],[46,22],[68,30],[84,44],[30,52],[55,48],[76,62],[42,72],[64,82]];
  const NESTS = [[30,28],[52,24],[73,30],[38,48],[60,52],[82,55],[47,72],[68,76]];
  // Same painted nest geography throughout: two actors and an escrow holding marker, not a third agent.
  const ROOST = {buyer:[15.3,43], worker:[75.6,46], escrow:[49.8,52]};
  const clamp = n => Math.max(0, Math.min(1, n));
  class Clock {
    constructor(stages) { this.stages=stages; this.index=0; this.elapsed=0; this.paused=false; this.hidden=false; this.reduced=false; }
    snapshot() { return {index:this.index, stageKey:this.stages[this.index].key, elapsed:this.elapsed,
      progress:this.elapsed/this.stages[this.index].duration_ms, paused:this.paused, hidden:this.hidden,
      reducedMotion:this.reduced, running:!this.paused&&!this.hidden&&!this.reduced}; }
    pause() { this.paused=true; }
    resume() { if(this.index===this.stages.length-1 && this.elapsed===this.stages[this.index].duration_ms)return; this.paused=false; }
    setHidden(value) { this.hidden=!!value; }
    setReduced(value) { this.reduced=!!value; }
    setStage(index) {
      if(!Number.isInteger(index)||index<0||index>=this.stages.length)throw new RangeError('Unknown replay stage');
      this.index=index; this.elapsed=0;
    }
    setProgress(value) { if(!Number.isFinite(value))throw new RangeError('Invalid progress'); this.elapsed=clamp(value)*this.stages[this.index].duration_ms; }
    restart() { this.setStage(0); }
    advance(ms) {
      if(!this.snapshot().running || !Number.isFinite(ms) || ms<=0)return;
      this.elapsed+=ms;
      while(this.elapsed>=this.stages[this.index].duration_ms) {
        const duration=this.stages[this.index].duration_ms;
        if(this.index===this.stages.length-1) {this.elapsed=duration;this.pause();break;}
        this.elapsed-=duration;this.index++;
      }
    }
  }
  function simulatedRoutes(data, view, projectId) {
    const agents=data.agents.filter(a=>view==='world'||a.project_id===projectId);
    // A bounded, deterministic sample, prioritizing four actual in-flight rows.
    const flights=agents.filter(a=>a.state==='in_flight').slice(0,4);
    const resting=agents.filter(a=>a.state!=='in_flight').slice(0,Math.max(4,8-flights.length));
    return [...flights,...resting].slice(0,8).map((a,i)=>{
      const number=Number(a.id.match(/\d+$/)[0]);
      const anchor=view==='world'?data.projects.findIndex(p=>p.id===a.project_id):number%NESTS.length;
      const anchors=view==='world'?POS:NESTS;
      return {id:a.id,projectId:a.project_id,state:a.state,moving:a.state==='in_flight',
        from:anchors[anchor],to:anchors[(anchor+1+number%2)%anchors.length],
        phase:i/8,period:12000+(number%3)*1500,kind:'commute',role:'simulated'};
    });
  }
  function replayRoutes(key) {
    const {buyer,worker,escrow}=ROOST;
    const rests=Object.entries({buyer,worker}).map(([actor,p])=>({id:'roost-'+actor,from:p,to:p,moving:false,role:'perched'}));
    let route;
    if(key==='posted')route={from:buyer,to:worker,kind:'signal',role:'signal'};
    if(key==='refusal_local')route={from:worker,to:[62,39],kind:'refusal',role:'courier'};
    if(key==='refusal_http')route={from:worker,to:[31,39],kind:'refusal',role:'courier'};
    if(key==='proposed')route={from:worker,to:buyer,kind:'proposal',role:'courier'};
    if(key==='escrow')route={from:buyer,to:escrow,kind:'signal',role:'signal'};
    if(key==='delivered')route={from:worker,to:buyer,kind:'delivery',role:'courier',carry:true};
    if(key==='verified')route={from:buyer,to:buyer,kind:'review',role:'signal'};
    if(key==='settled')route={from:escrow,to:buyer,kind:'signal',role:'signal'};
    return route?[...rests,{...route,id:'focal',moving:route.kind!=='review'}]:rests;
  }
  function pose(route, progress) {
    const p=clamp(progress);
    if(!route.moving)return {point:[...route.from],angle:0,mirror:1,frame:'perched',active:false};
    const returning=route.kind==='refusal'&&p>.5;
    let t=route.kind==='refusal'?(p<=.5?p*2:(1-p)*2):clamp((p-.08)/.78);
    // A commuter makes a bounded out-and-back trip; no teleport on loop wrap.
    if(route.kind==='commute') t=p<=.5?p*2:(1-p)*2;
    t=t*t*(3-2*t);
    const dx=route.to[0]-route.from[0],dy=route.to[1]-route.from[1];
    const point=t===0?[...route.from]:t===1?[...route.to]:[route.from[0]+dx*t,route.from[1]+dy*t-Math.sin(Math.PI*t)*(route.kind==='delivery'?5:3)];
    const backwards=returning||(route.kind==='commute'&&p>.5);
    const mirror=(dx<0?-1:1)*(backwards?-1:1);
    const angle=Math.max(-18,Math.min(18,Math.atan2(dy,Math.abs(dx))*180/Math.PI))*(backwards?-1:1);
    return {point,angle,mirror,frame:route.carry?'carry':(t===0||t===1?'perched':'flight_'+(1+Math.floor(p*18)%3)),active:t>0&&t<1};
  }
  return {Clock,simulatedRoutes,replayRoutes,pose,POS,NESTS,ROOST};
});
