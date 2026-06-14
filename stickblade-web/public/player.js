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
// Per-weapon blade geometry — must match WEAPON_GEOMETRY in stickblade/weapons.py.
const WEAPON_GEO = {
  sword:  {pommel:-34, handle:-26, tip:52, tipFrac:0.72, w:5, hilt:true},
  dagger: {pommel:-18, handle:-12, tip:22, tipFrac:0.55, w:4, hilt:true},
  spear:  {pommel:-10, handle: -6, tip:98, tipFrac:0.85, w:4, hilt:false},
};
const SW = WEAPON_GEO.sword;   // legacy alias
const HEAD_R = 12, START_HP = 100;

const W = R.meta.width, H = R.meta.height, FPS = R.meta.fps;
const cv = document.getElementById("cv"), ctx = cv.getContext("2d");
// Resolution-aware sizing: render at the canvas's actual on-screen size
// (capped at DPR<=1.5) instead of always 1280x720 — on a 400px-wide phone
// the old code drew ~5.5x more pixels per frame than the user could see.
function fitCanvas() {
  const cssW = cv.clientWidth || W;
  const dpr  = Math.min(window.devicePixelRatio || 1, 1.5);
  const targetW = Math.max(320, Math.round(cssW * dpr));
  const targetH = Math.round(targetW * (H / W));
  if (cv.width !== targetW || cv.height !== targetH) {
    cv.width = targetW; cv.height = targetH;
    // bg cache becomes stale on resize — rebuild lazily by clearing the flag.
    bgDirty = true;
  }
}
let bgDirty = true;
// Defer the first fit until the canvas has a real CSS width (React mount).
requestAnimationFrame(fitCanvas);
window.addEventListener("resize", () => { bgDirty = true; fitCanvas(); }, { passive: true });

/* ---------- background (cached; rebuilt on resize) ---------- */
const bg = document.createElement("canvas");
function buildBg() {
  bg.width = W; bg.height = H;       // engine coords; ctx.scale handles display
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
  bgDirty = false;
}
buildBg();

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

/* ---------- audio (synthesized; CSP-clean, no external assets) ---------- */
let ac = null, muted = false;
function audio(){
  if (muted) return null;
  if (!ac) {
    try { ac = new (window.AudioContext || window.webkitAudioContext)(); }
    catch (_) { muted = true; return null; }
  }
  // Browsers suspend the context until a user gesture; resume on first call.
  if (ac.state === "suspended") { try { ac.resume(); } catch(_){} }
  return ac;
}
function tone(freq, dur, type="sine", vol=0.18, sweepTo=null){
  const c = audio(); if (!c) return;
  const t0 = c.currentTime;
  const osc = c.createOscillator();
  const g   = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t0);
  if (sweepTo != null) osc.frequency.exponentialRampToValueAtTime(
    Math.max(20, sweepTo), t0 + dur);
  g.gain.setValueAtTime(vol, t0);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  osc.connect(g).connect(c.destination);
  osc.start(t0); osc.stop(t0 + dur + 0.02);
}
function noiseBurst(dur=0.07, vol=0.12, lp=2400){
  const c = audio(); if (!c) return;
  const buf = c.createBuffer(1, Math.ceil(c.sampleRate*dur), c.sampleRate);
  const d = buf.getChannelData(0);
  for (let i=0;i<d.length;i++) d[i] = (Math.random()*2-1)*(1-i/d.length);
  const src = c.createBufferSource(); src.buffer = buf;
  const g = c.createGain(); g.gain.value = vol;
  const f = c.createBiquadFilter(); f.type = "lowpass"; f.frequency.value = lp;
  src.connect(f).connect(g).connect(c.destination);
  src.start();
}
function sfxClash(){ tone(1850, 0.10, "square", 0.10, 600); noiseBurst(0.06, 0.10, 5000); }
function sfxHit(d, sharp){
  if (sharp){
    // wet sword strike
    tone(420, 0.16, "sawtooth", 0.16, 110);
    noiseBurst(0.10, 0.18, 1600);
  } else {
    // blunt thud
    tone(110, 0.18, "sine", 0.20, 55);
    noiseBurst(0.05, 0.10, 700);
  }
}
function sfxLethal(){
  // hit-stop chime + low boom
  tone(880, 0.18, "triangle", 0.18, 440);
  tone(1320, 0.30, "triangle", 0.10, 660);
  tone(55,  0.45, "sine",     0.22, 30);
}
function sfxArrow(){ noiseBurst(0.18, 0.08, 4000); tone(1400, 0.18, "sine", 0.04, 700); }
function sfxWin(){
  const c = audio(); if (!c) return;
  [523.25, 659.25, 783.99, 1046.5].forEach((f, i) =>
    setTimeout(() => tone(f, 0.22, "triangle", 0.14), i*110));
}

/* ---------- fx state (client-side particles) ---------- */
let blood=[], stains=[], sparks=[], numbers=[], shake=0, slowmo=0, flash=0;
// Phones get half the particle counts so heavy turns don't tank the framerate.
const LOW_FX = typeof window !== "undefined" &&
  (window.matchMedia && window.matchMedia("(max-width: 720px)").matches);
const FX_MUL = LOW_FX ? 0.5 : 1;
function spawnEvent(e){
  if (e.k === "clash") {
    const count = Math.round(10 * FX_MUL);
    for (let i=0;i<count;i++){ const a=Math.random()*6.283, s=60+Math.random()*180;
      sparks.push([e.x,e.y,Math.cos(a)*s,Math.sin(a)*s,0.15+Math.random()*0.25]); }
    shake = Math.max(shake,3);
    sfxClash();
    return;
  }
  const n = e.s ? Math.min(Math.round(46 * FX_MUL), Math.round((6+e.d*1.6) * FX_MUL)) : Math.round(3 * FX_MUL);
  for (let i=0;i<n;i++){ const a=Math.random()*6.283, s=40+Math.random()*(90+e.d*9);
    blood.push([e.x,e.y,Math.cos(a)*s,Math.sin(a)*s+80,0.5+Math.random()*0.8,1.5+Math.random()*2.1]); }
  if (e.s) { numbers.push([e.x,e.y+18, e.l?"FATAL!":("-"+e.d.toFixed(0)),
                           e.l?"#ffdc3c":"#ff5a5a", 1.4]);
             shake = Math.max(shake, Math.min(14, 3+e.d*0.35)); }
  else numbers.push([e.x,e.y+18,"blunt","#aaaebe",0.9]);
  if (e.l) { slowmo = 2.2; flash = 0.35; shake = 16; sfxLethal(); }
  else      sfxHit(e.d, e.s);
}
function stepFx(dt){
  for (const arr of [blood,sparks]){
    const g = arr===blood ? -900 : -400;
    for (const p of arr){ p[0]+=p[2]*dt; p[1]+=p[3]*dt; p[3]+=g*dt; p[4]-=dt;
      if (arr===blood && p[1] < R.meta.floor_y+3 && p[3]<0){
        const cap = LOW_FX ? 120 : 260;
        if (stains.length<cap) stains.push([p[0], R.meta.floor_y+Math.random()*3, p[5]*(0.9+Math.random()*0.8)]);
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
  const geo = WEAPON_GEO[WEAPON] || WEAPON_GEO.sword;
  const span = geo.tip - geo.handle, tipY = geo.handle + geo.tipFrac*span;
  const fc = liveFacing(frame, fi, meta);
  // blade body
  line(local(b,0,0), local(b,0,geo.tip), geo.w, "#d6dae6", ox, oy);

  if (WEAPON === "spear") {
    // shaft sharpened? — colour the mid section
    if (sharp.includes("shaft"))
      line(local(b,0,6), local(b,0,tipY), 3, "#ff4646", ox, oy);
    if (sharp.includes("tip"))
      line(local(b,0,tipY), local(b,0,geo.tip), 6, "#ff4646", ox, oy);
    // butt cap
    const pm = local(b,0,geo.pommel);
    ctx.fillStyle = sharp.includes("butt") ? "#ff4646" : "#a98050";
    ctx.beginPath(); ctx.arc(sx(pm[0],ox), sy(pm[1],oy), 5, 0, 7); ctx.fill();
    return;
  }

  // sword / dagger
  if (sharp.includes("edge"))
    line(local(b, fc*2.4, 2), local(b, fc*2.4, tipY), 2, "#ff4646", ox, oy);
  if (sharp.includes("back_edge"))
    line(local(b,-fc*2.4, 2), local(b,-fc*2.4, tipY), 2, "#ff4646", ox, oy);
  if (sharp.includes("tip"))
    line(local(b,0,tipY), local(b,0,geo.tip), geo.w, "#ff4646", ox, oy);
  if (geo.hilt) {
    line(local(b,-9,-2), local(b,9,-2), 4, "#d4af60", ox, oy);
    line(local(b,0,-3), local(b,0,geo.handle), 6, "#60462e", ox, oy);
    const pm = local(b,0,geo.pommel);
    ctx.fillStyle = sharp.includes("pommel") ? "#ff4646" : "#d4af60";
    ctx.beginPath(); ctx.arc(sx(pm[0],ox), sy(pm[1],oy), 5, 0, 7); ctx.fill();
  }
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
  // arena badge (top-right under the HP bar, only when non-default)
  const arena = R.meta.arena || "normal";
  if (arena !== "normal") {
    const txt = arena === "ice" ? "❄ ICE FLOOR" : "🌙 LOW GRAVITY";
    ctx.font = "bold 12px Arial";
    ctx.textAlign = "right";
    ctx.fillStyle = arena === "ice" ? "#88d8ff" : "#c9b8ff";
    ctx.fillText(txt, W - 40, 86);
  }
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
// Pre-fight trash talk bubble pinned over each fighter's head. Fades in/out.
function drawQuip(text, frame, fi, meta, alpha){
  if (!text || alpha <= 0) return;
  const head = bodyAt(frame, fi, 1);     // body index 1 = head
  const lines = wrap(text, 28);
  ctx.font = "italic 14px Arial";
  const lw = Math.max(...lines.map(l => ctx.measureText(l).width));
  const w = lw + 22, h = 18 * lines.length + 14;
  const hx = sx(head[0], 0), hy = sy(head[1], 0);
  let x = hx - w/2;
  let y = hy - h - 22;
  // keep on-screen
  if (x < 8) x = 8;
  if (x + w > W - 8) x = W - 8 - w;
  if (y < 8) y = hy + 30;
  ctx.save();
  ctx.globalAlpha = alpha;
  // bubble body
  ctx.fillStyle = "rgba(8,9,15,0.92)";
  rr(x, y, w, h, 10); ctx.fill();
  ctx.strokeStyle = meta.color;
  ctx.lineWidth = 2;
  rr(x, y, w, h, 10); ctx.stroke();
  // tail toward head
  ctx.beginPath();
  const tipx = Math.max(x + 14, Math.min(x + w - 14, hx));
  ctx.moveTo(tipx - 7, y + h);
  ctx.lineTo(tipx + 7, y + h);
  ctx.lineTo(hx,       hy - 12);
  ctx.closePath();
  ctx.fillStyle = "rgba(8,9,15,0.92)";
  ctx.fill();
  ctx.strokeStyle = meta.color;
  ctx.stroke();
  // text
  ctx.fillStyle = "#f5f6fb";
  ctx.textAlign = "left";
  lines.forEach((l, i) => ctx.fillText(l, x + 11, y + 20 + i * 18));
  ctx.restore();
}
const QUIP_FADE_IN_END   = 18;     // frames
const QUIP_HOLD_END      = 110;    // frames (~3.6s @ 30fps)
const QUIP_FADE_OUT_END  = 140;
function quipAlpha(cursor) {
  if (cursor < QUIP_FADE_IN_END)  return cursor / QUIP_FADE_IN_END;
  if (cursor < QUIP_HOLD_END)     return 1;
  if (cursor < QUIP_FADE_OUT_END) return 1 - (cursor - QUIP_HOLD_END) / (QUIP_FADE_OUT_END - QUIP_HOLD_END);
  return 0;
}

/* ---------- playback loop ---------- */
if (!R || !R.frames || !R.frames.length || !R.meta) {
  showError(new Error("replay data is empty or malformed"));
  return window.__sbPlayer = { destroy(){}, isAlive(){ return false; } };
}
const total = R.frames.length;
let cursor = 0, playing = true, lastT = performance.now(), acc = 0;
let killcamPlayed = false, killcamActive = false;
// Find the lethal event frame (if any) for the auto killcam.
const lethalFrame = (() => {
  for (let i = R.events.length - 1; i >= 0; i--) if (R.events[i].l) return R.events[i].f;
  return -1;
})();
const KILLCAM_PREROLL = 90;   // frames to rewind = ~1.5 s at 60 fps
const bPlay=document.getElementById("bPlay"), scrub=document.getElementById("scrub"),
      timeEl=document.getElementById("time"), speedEl=document.getElementById("speed");

// Optional mute toggle (gracefully no-op if the button doesn't exist).
const bMute = document.getElementById("bMute");
if (bMute) {
  bMute.onclick = () => {
    muted = !muted;
    bMute.textContent = muted ? "🔇 Sound" : "🔊 Sound";
    bMute.setAttribute("aria-pressed", String(muted));
  };
}
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
  if (next>=total){
    playing = false;
    bPlay.textContent = "▶ Play";
    if (!killcamPlayed && lethalFrame > KILLCAM_PREROLL) {
      // Auto KILLCAM: rewind ~1.5 s before the lethal blow and replay
      // in slowmo. Triggered exactly once per replay load.
      killcamPlayed = true;
      killcamActive = true;
      slowmo = Math.max(slowmo, 3.0);
      setTimeout(() => {
        gotoFrame(lethalFrame - KILLCAM_PREROLL, true);
        playing = true;
        bPlay.textContent = "⏸ Pause";
        sfxWin();
      }, 650);
    } else {
      // Normal end-of-replay chime.
      if (!killcamPlayed) sfxWin();
      killcamPlayed = true;
    }
    return;
  }
  cursor = next;
  for (const e of (eventsByFrame[cursor]||[])) spawnEvent(e);
  while (thoughtIdx+1 < R.thoughts.length && R.thoughts[thoughtIdx+1].f<=cursor) thoughtIdx++;
  // End killcam mode a couple frames after the lethal hit so the slow-mo
  // covers the actual kill but doesn't drag on forever.
  if (killcamActive && lethalFrame >= 0 && cursor > lethalFrame + 24) {
    killcamActive = false;
  }
}
function render(){
  if (bgDirty) buildBg();
  const frame = R.frames[cursor];
  const ox = shake>0.3 ? (Math.random()*2-1)*shake : 0;
  const oy = shake>0.3 ? (Math.random()*2-1)*shake : 0;
  // Map engine coordinates (W x H = 1280x720) into the canvas's actual
  // pixel size, which on mobile may be just 600x337. This is the single
  // biggest perf win — every line/circle becomes ~5x cheaper to rasterize.
  const sX = cv.width  / W;
  const sY = cv.height / H;
  ctx.setTransform(sX, 0, 0, sY, 0, 0);
  ctx.drawImage(bg, 0, 0);
  drawFx(ox,oy);
  const over = frame[3]===1;
  drawFighter(frame,0,R.meta.p1, frame[0]<=0, ox,oy);
  drawWeapon(frame,0,R.meta.p1, ox,oy);
  drawFighter(frame,1,R.meta.p2, frame[1]<=0, ox,oy);
  drawWeapon(frame,1,R.meta.p2, ox,oy);
  drawHud(frame);
  const th = thoughtIdx>=0 ? R.thoughts[thoughtIdx] : null;
  if (th){ drawThought(th.a, R.meta.p1, 0); drawThought(th.b, R.meta.p2, 1); }
  // pre-fight trash talk bubbles (first ~3.6s of replay)
  const qa = R.meta.quips && R.meta.quips.a, qb = R.meta.quips && R.meta.quips.b;
  const qAlpha = quipAlpha(cursor);
  if (qAlpha > 0) {
    drawQuip(qa, frame, 0, R.meta.p1, qAlpha);
    drawQuip(qb, frame, 1, R.meta.p2, qAlpha);
  }
  if (flash>0){ ctx.fillStyle=`rgba(255,255,255,${0.8*flash})`; ctx.fillRect(0,0,W,H); }
  if (killcamActive){
    // Cinematic letterbox bars
    ctx.fillStyle = "rgba(0,0,0,0.65)";
    ctx.fillRect(0, 0, W, 48);
    ctx.fillRect(0, H-48, W, 48);
    ctx.fillStyle = "#ff3d5c";
    ctx.font = "bold 18px Arial";
    ctx.textAlign = "left";
    ctx.fillText("● KILLCAM", 22, 32);
    ctx.textAlign = "right";
    ctx.fillStyle = "#ffd65a";
    ctx.fillText("0.25× SLOW-MO", W-22, 32);
  }
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
  const slowFactor = killcamActive ? 0.25 : (slowmo>0 ? 0.22 : 1);
  const sp = parseFloat(speedEl.value) * slowFactor;
  if (playing){ acc += dt*FPS*sp; while (acc>=1){ acc--; advance(); } }
  stepFx(dt*(killcamActive ? 0.5 : (slowmo>0 ? 0.4 : 1)));
  render();
  } catch (e) { alive = false; showError(e); return; }
  requestAnimationFrame(loop);
}
// First user gesture unlocks the AudioContext on all browsers.
const _unlockAudio = () => { audio(); document.removeEventListener("pointerdown", _unlockAudio); };
document.addEventListener("pointerdown", _unlockAudio);

bPlay.onclick = ()=>{
  audio();   // ensure context is active on play toggles
  playing=!playing;
  if (playing && cursor>=total-1){
    // Manual replay restart resets the killcam-once flag.
    killcamPlayed = false; killcamActive = false;
    gotoFrame(0,true);
  }
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
