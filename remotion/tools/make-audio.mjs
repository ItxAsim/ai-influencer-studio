// Procedural ambient bed (garden at dusk) — no external deps.
// Faint afternoon birdsong + soft breeze through leaves, no voice, no music.
// Writes a 16-bit mono WAV into public/audio/. The ends are crossfaded so the
// bed loops cleanly with the video.
//
//   node tools/make-audio.mjs
//
import {mkdirSync, writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, join} from 'node:path';

const SR = 44100;
const SECONDS = 10;
const OUT = join(dirname(fileURLToPath(import.meta.url)), '..', 'public', 'audio');
mkdirSync(OUT, {recursive: true});

const TAU = Math.PI * 2;

// Deterministic PRNG so every run produces the same bed.
let seed = 1337;
const rand = () => {
  seed = (seed * 1664525 + 1013904223) >>> 0;
  return seed / 4294967296;
};

// Render a little longer than needed so the tail can be folded onto the head.
const FOLD = 0.6;
const N = Math.ceil((SECONDS + FOLD) * SR);
const buf = new Float32Array(N);

// ----- breeze: low-passed noise with slow gusting ------------------------------
{
  let lp1 = 0;
  let lp2 = 0;
  for (let i = 0; i < N; i++) {
    const t = i / SR;
    const gust =
      0.55 +
      0.25 * Math.sin(TAU * 0.13 * t + 0.7) +
      0.15 * Math.sin(TAU * 0.31 * t + 2.1);
    const white = rand() * 2 - 1;
    lp1 += 0.035 * (white - lp1); // body of the wind
    lp2 += 0.25 * (white - lp2); // leaf rustle (brighter)
    const rustle = (lp2 - lp1) * (0.4 + 0.6 * Math.max(0, Math.sin(TAU * 0.21 * t)));
    buf[i] += (lp1 * 1.6 + rustle * 0.25) * gust * 0.22;
  }
}

// ----- birdsong: short swept chirps in small phrases ---------------------------
function chirp(t0, dur, f0, f1, gain) {
  const n0 = Math.floor(t0 * SR);
  const len = Math.floor(dur * SR);
  let phase = 0;
  for (let i = 0; i < len; i++) {
    const idx = n0 + i;
    if (idx >= N) break;
    const u = i / len;
    const f = f0 + (f1 - f0) * Math.sin(u * Math.PI * 0.5) + 180 * Math.sin(TAU * 38 * u * dur);
    phase += (TAU * f) / SR;
    const env = Math.sin(Math.PI * u) ** 2;
    buf[idx] += (Math.sin(phase) + 0.18 * Math.sin(2 * phase)) * env * gain;
  }
}

// Two "birds" at different distances, phrases scattered through the take.
const birds = [
  {base: 3400, spread: 900, gain: 0.05, every: 2.3},
  {base: 4600, spread: 1200, gain: 0.028, every: 3.1},
];
for (const b of birds) {
  let t = rand() * 0.8 + 0.3;
  while (t < SECONDS + FOLD - 0.5) {
    const notes = 2 + Math.floor(rand() * 4);
    for (let k = 0; k < notes; k++) {
      const f0 = b.base + (rand() - 0.5) * b.spread;
      const f1 = f0 + (rand() - 0.3) * b.spread;
      chirp(t, 0.06 + rand() * 0.09, f0, f1, b.gain * (0.7 + rand() * 0.3));
      t += 0.1 + rand() * 0.12;
    }
    t += b.every * (0.6 + rand() * 0.8);
  }
}

// ----- fold tail onto head for a seamless loop ---------------------------------
const L = Math.floor(SECONDS * SR);
const F = Math.floor(FOLD * SR);
const out = new Float32Array(L);
for (let i = 0; i < L; i++) out[i] = buf[i];
for (let i = 0; i < F; i++) {
  const w = i / F; // head fades in as the folded tail fades out
  out[i] = buf[i] * w + buf[L + i] * (1 - w);
}

// Normalise quietly — this is a ducked ambient bed.
let peak = 0;
for (const s of out) peak = Math.max(peak, Math.abs(s));
const scale = 0.35 / (peak || 1);

const data = Buffer.alloc(L * 2);
for (let i = 0; i < L; i++) {
  data.writeInt16LE(Math.round(Math.max(-1, Math.min(1, out[i] * scale)) * 32767), i * 2);
}
const header = Buffer.alloc(44);
header.write('RIFF', 0);
header.writeUInt32LE(36 + data.length, 4);
header.write('WAVE', 8);
header.write('fmt ', 12);
header.writeUInt32LE(16, 16);
header.writeUInt16LE(1, 20);
header.writeUInt16LE(1, 22);
header.writeUInt32LE(SR, 24);
header.writeUInt32LE(SR * 2, 28);
header.writeUInt16LE(2, 32);
header.writeUInt16LE(16, 34);
header.write('data', 36);
header.writeUInt32LE(data.length, 40);
writeFileSync(join(OUT, 'ambient.wav'), Buffer.concat([header, data]));
console.log('wrote public/audio/ambient.wav');
