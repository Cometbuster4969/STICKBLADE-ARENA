"use strict";
/* Stickblade replay player. Usage: window.__sbPlayer = initPlayer(replayData)
   Expects DOM ids: cv, bPlay, bRestart, scrub, time, speed, subtitle, cardResult.
   Returns {destroy}. Safe to call repeatedly (tears down previous instance). */
function initPlayer(R) {
  if (window.__sbPlayer) { window.__sbPlayer.destroy(); }
  let alive = true;
  // ---- compat: roundRect is missing on older browsers (pre-Chrome99/Saf16/FF112)
  (function polyfillRoundRect(){
    const CRP = (typeof CanvasRenderingContext2D !== "undefined")
      ? CanvasRenderingContext2D.prototype : null;
    if (CRP && !CRP.roundRect) {
      CRP.roundRect = function (x, y, w, h, r) {
        if (typeof r === "number") r = [r, r, r, r];
        else if (Array.isArray(r)) { while (r.length < 4) r.push(r[r.length-1] ?? 0); }
        else r = [0, 0, 0, 0];
        this.moveTo(x + r[0], y);
        this.arcTo(x + w, y, x + w, y + h, r[1]);
        this.arcTo(x + w, y + h, x, y + h, r[2]);
        this.arcTo(x, y + h, x, y, r[3]);
        this.arcTo(x, y, x + w, y, r[0]);
        this.closePath();
        return this;
      };
    }
  })();
  // ---- never fail silently: surface errors on the page
  function showError(e) {
    try {
      const el = document.getElementById("subtitle");
      if (el) { el.style.display = "block"; el.style.color = "#ff6464";
        el.textContent = "Replay player error: " + (e && e.message ? e.message : e); }
      const cvEl = document.getElementById("cv");
      if (cvEl) {
        const c = cvEl.getContext("2d");
        c.fillStyle = "#181a24"; c.fillRect(0, 0, cvEl.width, cvEl.height);
        c.fillStyle = "#ff6464"; c.font = "bold 22px Arial"; c.textAlign = "center";
        c.fillText("⚠ Replay player error — see message above / console",
                   cvEl.width / 2, cvEl.height / 2);
      }
      console.error("[stickblade player]", e);
    } catch (_) {}
  }



/* ---------- constants mirrored from the Python engine ---------- */
const BODY = ["torso","head","uarm","farm","off_uarm","off_farm",
              "thigh_f","shin_f","thigh_b","shin_b","sword"];
const FLAIL_EXTRA = 4;          // 3 links + ball appended per fighter
const WEAPON = (R.meta.weapon || "sword");
  if (R.v && R.v > 2) {
    showError(new Error("replay format v" + R.v +
      " is newer than this player — hard-refresh the page (Ctrl+Shift+R)"));
    return window.__sbPlayer = { destroy(){}, isAlive(){ return false; } };
  }
const HALF = {torso:28, uarm:13, farm:12, off_uarm:13, off_farm:12,
              thigh_f:15, shin_f:15, thigh_b:15, shin_b:15};
const WIDTHS = {torso:12, uarm:9, farm:8, off_uarm:8, off_farm:7,
                thigh_f:10, shin_f:9, thigh_b:9, shin_b:8};
const DARKSET = new Set(["off_uarm","off_farm","thigh_b","shin_b"]);
const SW = {pommel:-34, handle:-26, tip:52, tipFrac:0.72};
const HEAD_R = 12, START_HP = 100;

const W = R.meta.width, H = R.meta.height, FPS = R.meta.fps;
const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
cv.width = W; cv.height = H;

/* ---------- background (drawn once) ---------- */
const bg = document.createElement("canvas"); bg.width = W; bg.height = H;
{
  const b = bg.getContext("2d");
  const g = b.createLinearGradient(0,0,0,H);
  g.addColorStop(0,"#10121a"); g.addColorStop(1,"#262a3a");
  b.fillStyle = g; b.fillRect(0,0,W,H);
  const fy = H - R.meta.floor_y;
  b.fillStyle = "#34384a"; b.fillRect(0,fy,W,H-fy);
  b.strokeStyle = "#4a5068"; b.lineWidth = 3;
  b.beginPath(); b.moveTo(0,fy); b.lineTo(W,fy); b.stroke();
  b.strokeStyle = "#2e3242"; b.lineWidth = 2;
  for (let x=0; x<W; x+=64) { b.beginPath(); b.moveTo(x,fy+8); b.lineTo(x-30,H); b.stroke(); }
  b.fillStyle = "rgba(255,255,255,0.05)";
  b.beginPath(); b.ellipse(W/2, fy+20, 430, 140, 0, 0, 7); b.fill();
}

/* ---------- replay indexing ---------- */
const NB = BODY.length + (WEAPON === "flail" ? FLAIL_EXTRA : 0);
const STRIDE = 3, OFF = 4;                           // hp1,hp2,turn,over
function bodyAt(frame, fi, bi) {                     // fighter 0/1, body index
  const o = OFF + (fi*NB + bi)*STRIDE;
  return [frame[o], frame[o+1], frame[o+2]];
}
function arrowsAt(frame, fi) {                       // bow: parse arrow block
  if (WEAPON !== "bow") return [];
  let o = OFF + 2*NB*STRIDE;
  for (let f = 0; f < 2; f++) {
    const n = frame[o]; o++;
    if (f === fi) {
      const out = [];
      for (let i = 0; i < n; i++) out.push([frame[o+i*3], frame[o+i*3+1], frame[o+i*3+2]]);
      return out;
    }
    o += n*3;
  }
  return [];
}
const eventsByFrame = {};
for (const e of R.events) (eventsByFrame[e.f] ||= []).push(e);
let thoughtIdx = -1;

/* ---------- fx state (client-side particles) ---------- */
let blood=[], stains=[], sparks=[], numbers=[], shake=0, slowmo=0, flash=0;
function spawnEvent(e){
  if (e.k === "clash") {
    for (let i=0;i<10;i++){ const a=Math.random()*6.283, s=60+Math.random()*180;
      sparks.push([e.x,e.y,Math.cos(a)*s,Math.sin(a)*s,0.15+Math.random()*0.25]); }
    shake = Math.max(shake,3); return;
  }
  const n = e.s ? Math.min(46, 6+e.d*1.6) : 3;
  for (let i=0;i<n;i++){ const a=Math.random()*6.283, s=40+Math.random()*(90+e.d*9);
    blood.push([e.x,e.y,Math.cos(a)*s,Math.sin(a)*s+80,0.5+Math.random()*0.8,1.5+Math.random()*2.1]); }
  if (e.s) { numbers.push([e.x,e.y+18, e.l?"FATAL!":("-"+e.d.toFixed(0)),
                           e.l?"#ffdc3c":"#ff5a5a", 1.4]);
             shake = Math.max(shake, Math.min(14, 3+e.d*0.35)); }
  else numbers.push([e.x,e.y+18,"blunt","#aaaebe",0.9]);
  if (e.l) { slowmo = 2.2; flash = 0.35; shake = 16; }
}
function stepFx(dt){
  for (const arr of [blood,sparks]){
    const g = arr===blood ? -900 : -400;
    for (const p of arr){ p[0]+=p[2]*dt; p[1]+=p[3]*dt; p[3]+=g*dt; p[4]-=dt;
      if (arr===blood && p[1] < R.meta.floor_y+3 && p[3]<0){
        if (stains.length<260) stains.push([p[0], R.meta.floor_y+Math.random()*3, p[5]*(0.9+Math.random()*0.8)]);
        p[4]=0; } }
  }
  blood = blood.filter(p=>p[4]>0); sparks = sparks.filter(p=>p[4]>0);
  for (const n of numbers){ n[1]+=34*dt; n[4]-=dt; }
  numbers = numbers.filter(n=>n[4]>0);
  shake=Math.max(0,shake-38*dt); slowmo=Math.max(0,slowmo-dt); flash=Math.max(0,flash-dt);
}
function resetFx(){ blood=[];stains=[];sparks=[];numbers=[];shake=0;slowmo=0;flash=0; }

/* ---------- drawing ---------- */
function sx(x,ox){ return x+ox; }
function sy(y,oy){ return H-y+oy; }
function local(b, lx, ly){            // body [x,y,a] local->world
  const c=Math.cos(b[2]), s=Math.sin(b[2]);
  return [b[0]+lx*c-ly*s, b[1]+lx*s+ly*c];
}
function line(p,q,w,col,ox,oy){
  ctx.strokeStyle=col; ctx.lineWidth=w; ctx.lineCap="round";
  ctx.beginPath(); ctx.moveTo(sx(p[0],ox),sy(p[1],oy));
  ctx.lineTo(sx(q[0],ox),sy(q[1],oy)); ctx.stroke();
}
function drawFighter(frame, fi, meta, dead, ox, oy){
  const col = dead ? shade(meta.color,0.45) : meta.color;
  const dark = dead ? shade(meta.dark,0.45) : meta.dark;
  const order = [8,9,4,5,0,6,7,2,3];   // back legs/arms, torso, front legs/arms
  for (const bi of order){
    const nm = BODY[bi], b = bodyAt(frame,fi,bi);
    const h = HALF[nm];
    line(local(b,0,h), local(b,0,-h), WIDTHS[nm], DARKSET.has(nm)?dark:col, ox, oy);
  }
  const hb = bodyAt(frame,fi,1);
  ctx.fillStyle = col;
  ctx.beginPath(); ctx.arc(sx(hb[0],ox), sy(hb[1],oy), HEAD_R, 0, 7); ctx.fill();
  const eye = local(hb, liveFacing(frame, fi, meta)*5.5, 2);
  ctx.strokeStyle="#0f1016"; ctx.fillStyle="#0f1016"; ctx.lineWidth=2;
  if (!dead){ ctx.beginPath(); ctx.arc(sx(eye[0],ox), sy(eye[1],oy), 2, 0, 7); ctx.fill(); }
  else { const ex=sx(eye[0],ox), ey=sy(eye[1],oy);
    ctx.beginPath(); ctx.moveTo(ex-3,ey-3); ctx.lineTo(ex+3,ey+3);
    ctx.moveTo(ex-3,ey+3); ctx.lineTo(ex+3,ey-3); ctx.stroke(); }
}
function liveFacing(frame, fi, meta){
  const me = bodyAt(frame, fi, 0), foe = bodyAt(frame, 1 - fi, 0);
  const dx = foe[0] - me[0];
  return Math.abs(dx) > 2 ? (dx > 0 ? 1 : -1) : meta.facing;
}
function drawWeapon(frame, fi, meta, ox, oy){
  if (WEAPON === "flail") return drawFlail(frame, fi, meta, ox, oy);
  if (WEAPON === "bow")   return drawBow(frame, fi, meta, ox, oy);
  drawSword(frame, fi, meta, ox, oy);
}
function drawFlail(frame, fi, meta, ox, oy){
  const sharp = R.meta.sharp;
  const hb = bodyAt(frame,fi,10);
  line(local(hb,0,-8), local(hb,0,26), 6,
       sharp.includes("handle") ? "#ff4646" : "#60462e", ox, oy);
  const ccol = sharp.includes("chain") ? "#ff4646" : "#a0a4b2";
  for (let i=0;i<3;i++){
    const lb = bodyAt(frame,fi,11+i);
    line(local(lb,0,0), local(lb,0,9), 3, ccol, ox, oy);
  }
  const bb = bodyAt(frame,fi,14);
  const bp = [sx(bb[0],ox), sy(bb[1],oy)];
  // ball speed estimated from previous frame for spike glow
  let fast = false;
  if (cursor>0){
    const pb = bodyAt(R.frames[cursor-1],fi,14);
    const dt = 1/FPS;
    fast = Math.hypot(bb[0]-pb[0], bb[1]-pb[1])/dt >= 200;
  }
  const ballSharp = (sharp.includes("spikes") && fast) || sharp.includes("ball");
  ctx.fillStyle = ballSharp ? "#ff4646" : "#787c8c";
  ctx.beginPath(); ctx.arc(bp[0], bp[1], 7, 0, 7); ctx.fill();
  if (sharp.includes("spikes")){
    ctx.strokeStyle = fast ? "#ff4646" : "#9696a2"; ctx.lineWidth = 2;
    for (let k=0;k<8;k++){
      const a = k*Math.PI/4 + bb[2];
      ctx.beginPath(); ctx.moveTo(bp[0], bp[1]);
      ctx.lineTo(bp[0]+Math.cos(a)*13, bp[1]-Math.sin(a)*13); ctx.stroke();
    }
  }
}
function drawBow(frame, fi, meta, ox, oy){
  const sharp = R.meta.sharp;
  const bb = bodyAt(frame,fi,10);
  const fcb = liveFacing(frame, fi, meta);
  const top = local(bb,0,46), bot = local(bb,0,-46), mid = local(bb,fcb*7,0);
  ctx.strokeStyle = sharp.includes("bow_limb") ? "#ff4646" : "#8c6032";
  ctx.lineWidth = 4; ctx.lineCap = "round";
  ctx.beginPath();
  ctx.moveTo(sx(bot[0],ox), sy(bot[1],oy));
  ctx.lineTo(sx(mid[0],ox), sy(mid[1],oy));
  ctx.lineTo(sx(top[0],ox), sy(top[1],oy));
  ctx.stroke();
  line(top, bot, 1, "#d2d4de", ox, oy);
  // arrows
  const headC = sharp.includes("arrowhead") ? "#ff4646" : "#c8ccd6";
  const shaftC = sharp.includes("arrow_shaft") ? "#ff4646" : "#967850";
  for (const [axp, ayp, aa] of arrowsAt(frame, fi)){
    const ca = Math.cos(aa), sa = Math.sin(aa);
    const pt = (ly) => [axp - ly*sa, ayp + ly*ca];
    line(pt(0), pt(24), 2, shaftC, ox, oy);
    line(pt(24), pt(34), 3, headC, ox, oy);
  }
}
function drawSword(frame, fi, meta, ox, oy){
  const b = bodyAt(frame,fi,10), sharp = R.meta.sharp;
  const span = SW.tip - SW.handle, tipY = SW.handle + SW.tipFrac*span;
  const fc = liveFacing(frame, fi, meta);
  line(local(b,0,0), local(b,0,SW.tip), 5, "#d6dae6", ox, oy);
  if (sharp.includes("edge"))
    line(local(b, fc*2.4, 2), local(b, fc*2.4, tipY), 2, "#ff4646", ox, oy);
  if (sharp.includes("back_edge"))
    line(local(b,-fc*2.4, 2), local(b,-fc*2.4, tipY), 2, "#ff4646", ox, oy);
  if (sharp.includes("tip"))
    line(local(b,0,tipY), local(b,0,SW.tip), 5, "#ff4646", ox, oy);
  line(local(b,-9,-2), local(b,9,-2), 4, "#d4af60", ox, oy);
  line(local(b,0,-3), local(b,0,SW.handle), 6, "#60462e", ox, oy);
  const pm = local(b,0,SW.pommel);
  ctx.fillStyle = sharp.includes("pommel") ? "#ff4646" : "#d4af60";
  ctx.beginPath(); ctx.arc(sx(pm[0],ox), sy(pm[1],oy), 5, 0, 7); ctx.fill();
}
function shade(hex,f){
  const n=parseInt(hex.slice(1),16);
  const r=(n>>16)*f|0, g=((n>>8)&255)*f|0, b=(n&255)*f|0;
  return `rgb(${r},${g},${b})`;
}
function drawFx(ox,oy){
  ctx.fillStyle="#6e1018";
  for (const s of stains){ ctx.beginPath(); ctx.arc(sx(s[0],ox),sy(s[1],oy),s[2],0,7); ctx.fill(); }
  ctx.fillStyle="#be1824";
  for (const p of blood){ ctx.beginPath(); ctx.arc(sx(p[0],ox),sy(p[1],oy),p[5],0,7); ctx.fill(); }
  ctx.fillStyle="#ffeba0";
  for (const p of sparks){ ctx.beginPath(); ctx.arc(sx(p[0],ox),sy(p[1],oy),2,0,7); ctx.fill(); }
  for (const n of numbers){
    ctx.globalAlpha = Math.min(1,n[4]); ctx.fillStyle=n[3];
    ctx.font="bold 21px Arial"; ctx.textAlign="center";
    ctx.fillText(n[2], sx(n[0],ox), sy(n[1],oy)); ctx.globalAlpha=1; }
}
function drawHud(frame){
  const [hp1,hp2,turn] = frame;
  const bar=(x,hp,col,right)=>{
    ctx.fillStyle="#3c181c"; rr(x,38,360,20,6); ctx.fill();
    const w=360*hp/START_HP;
    if (w>0){ ctx.fillStyle = hp>35?col:"#eb5046"; rr(right?x+360-w:x,38,w,20,6); ctx.fill(); }
    ctx.strokeStyle="#14161e"; ctx.lineWidth=2; rr(x,38,360,20,6); ctx.stroke();
  };
  bar(40,hp1,R.meta.p1.color,false); bar(W-400,hp2,R.meta.p2.color,true);
  ctx.textAlign="left"; ctx.font="bold 21px Arial";
  ctx.fillStyle=R.meta.p1.color; ctx.fillText(R.meta.p1.name,40,30);
  ctx.textAlign="right"; ctx.fillStyle=R.meta.p2.color; ctx.fillText(R.meta.p2.name,W-40,30);
  ctx.textAlign="left"; ctx.font="13px Arial"; ctx.fillStyle="#e8eaf4";
  ctx.fillText(hp1.toFixed(0), 408, 53);
  ctx.textAlign="right"; ctx.fillText(hp2.toFixed(0), W-408, 53);
  ctx.textAlign="center"; ctx.font="bold 40px Arial"; ctx.fillStyle="#e8eaf4";
  ctx.fillText(turn, W/2, 48);
  ctx.font="11px Arial"; ctx.fillStyle="#969aac"; ctx.fillText("TURN", W/2, 64);
  ctx.font="bold 14px Arial"; ctx.fillStyle="#ff4646";
  ctx.fillText(WEAPON.toUpperCase()+" — SHARP: "+R.meta.sharp.map(z=>z.toUpperCase()).join(" + "), W/2, 86);
}
function rr(x,y,w,h,r){ ctx.beginPath(); ctx.roundRect(x,y,w,h,r); }
function wrap(t,max){ const out=[]; let cur="";
  for (const w of t.split(" ")){ if ((cur+w).length<max) cur+=(cur?" ":"")+w;
    else {out.push(cur); cur=w;} } out.push(cur); return out.slice(0,4); }
function drawThought(text, meta, side){
  if (!text) return;
  const lines = wrap(text,40);
  ctx.font="13px Arial";
  const w = Math.max(...lines.map(l=>ctx.measureText(l).width))+20;
  const h = 16*lines.length+14, x = side? W-40-w : 40, y=104;
  ctx.fillStyle="rgba(12,13,20,0.85)"; rr(x,y,w,h,8); ctx.fill();
  ctx.strokeStyle=meta.color; ctx.globalAlpha=0.65; ctx.lineWidth=2;
  rr(x,y,w,h,8); ctx.stroke(); ctx.globalAlpha=1;
  ctx.fillStyle="#e8eaf4"; ctx.textAlign="left";
  lines.forEach((l,i)=>ctx.fillText(l, x+10, y+18+i*16));
}

/* ---------- playback loop ---------- */
if (!R || !R.frames || !R.frames.length || !R.meta) {
  showError(new Error("replay data is empty or malformed"));
  return window.__sbPlayer = { destroy(){}, isAlive(){ return false; } };
}
const total = R.frames.length;
let cursor = 0, playing = true, lastT = performance.now(), acc = 0;
const bPlay=document.getElementById("bPlay"), scrub=document.getElementById("scrub"),
      timeEl=document.getElementById("time"), speedEl=document.getElementById("speed");
scrub.max = total-1;
document.getElementById("subtitle").textContent =
  `${R.meta.p1.name}  vs  ${R.meta.p2.name}  ·  sharp: ${R.meta.sharp.join("+")}`;
{
  const res = R.meta.result || {};
  document.getElementById("cardResult").innerHTML =
    `<b>Result:</b> ${R.meta.winner || "unknown"}` +
    (res.turns !== undefined ? ` · ${res.turns} turns` : "") +
    (res.method ? ` · method: ${res.method}` : "");
}
function fmt(f){ const s=f/FPS; return Math.floor(s/60)+":"+String(Math.floor(s%60)).padStart(2,"0"); }

function gotoFrame(i, hard){
  if (hard){ resetFx();
    thoughtIdx = -1;
    for (let k=0;k<R.thoughts.length;k++) if (R.thoughts[k].f<=i) thoughtIdx=k;
  }
  cursor = Math.max(0, Math.min(total-1, i));
}
function advance(){
  const next = cursor+1;
  if (next>=total){ playing=false; bPlay.textContent="▶ Play"; return; }
  cursor = next;
  for (const e of (eventsByFrame[cursor]||[])) spawnEvent(e);
  while (thoughtIdx+1 < R.thoughts.length && R.thoughts[thoughtIdx+1].f<=cursor) thoughtIdx++;
}
function render(){
  const frame = R.frames[cursor];
  const ox = shake>0.3 ? (Math.random()*2-1)*shake : 0;
  const oy = shake>0.3 ? (Math.random()*2-1)*shake : 0;
  ctx.drawImage(bg,0,0);
  drawFx(ox,oy);
  const over = frame[3]===1;
  drawFighter(frame,0,R.meta.p1, frame[0]<=0, ox,oy);
  drawWeapon(frame,0,R.meta.p1, ox,oy);
  drawFighter(frame,1,R.meta.p2, frame[1]<=0, ox,oy);
  drawWeapon(frame,1,R.meta.p2, ox,oy);
  drawHud(frame);
  const th = thoughtIdx>=0 ? R.thoughts[thoughtIdx] : null;
  if (th){ drawThought(th.a, R.meta.p1, 0); drawThought(th.b, R.meta.p2, 1); }
  if (flash>0){ ctx.fillStyle=`rgba(255,255,255,${0.8*flash})`; ctx.fillRect(0,0,W,H); }
  if (over || cursor>=total-1){
    ctx.textAlign="center"; ctx.font="bold 44px Arial"; ctx.fillStyle="#ffdc5a";
    ctx.fillText(R.meta.winner, W/2, H/2-40);
  }
  scrub.value = cursor;
  timeEl.textContent = fmt(cursor)+" / "+fmt(total-1);
}
function loop(now){
  if (!alive) return;
  try {
  const dt = Math.min(0.1,(now-lastT)/1000); lastT = now;
  const sp = parseFloat(speedEl.value) * (slowmo>0?0.22:1);
  if (playing){ acc += dt*FPS*sp; while (acc>=1){ acc--; advance(); } }
  stepFx(dt*(slowmo>0?0.4:1));
  render();
  } catch (e) { alive = false; showError(e); return; }
  requestAnimationFrame(loop);
}
bPlay.onclick = ()=>{ playing=!playing;
  if (playing && cursor>=total-1) gotoFrame(0,true);
  bPlay.textContent = playing?"⏸ Pause":"▶ Play"; };
document.getElementById("bRestart").onclick = ()=>{ gotoFrame(0,true); playing=true; bPlay.textContent="⏸ Pause"; };
scrub.oninput = ()=>{ gotoFrame(parseInt(scrub.value), true); };
document.addEventListener("keydown",(e)=>{
  if (!alive) return;
  if (e.target && (e.target.tagName==="INPUT"||e.target.tagName==="SELECT")) return;
  if (e.code==="Space"){ e.preventDefault(); bPlay.onclick(); }
  if (e.code==="ArrowRight") { gotoFrame(cursor+1,true); }
  if (e.code==="ArrowLeft")  { gotoFrame(cursor-1,true); }
});
requestAnimationFrame(loop);
  window.__sbPlayer = { destroy(){ alive = false; },
    isAlive(){ return alive; }, showError };
  return window.__sbPlayer;
}
