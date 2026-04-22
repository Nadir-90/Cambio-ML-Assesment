/** @description Audio streaming from the VM desktop via WebSocket. */

import { el } from './utils.js';

let audioCtx = null;
let audioWs = null;
let audioEnabled = false;
const SAMPLE_RATE = 44100;
const CHANNELS = 2;

export function startAudio() {
  if (audioWs) return;

  audioCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: SAMPLE_RATE });

  const host = window.location.hostname || 'localhost';
  audioWs = new WebSocket(`ws://${host}:4680`);
  audioWs.binaryType = 'arraybuffer';

  let nextTime = 0;

  audioWs.onmessage = (e) => {
    const raw = new Int16Array(e.data);
    const frames = raw.length / CHANNELS;
    if (frames === 0) return;

    const buf = audioCtx.createBuffer(CHANNELS, frames, SAMPLE_RATE);
    for (let ch = 0; ch < CHANNELS; ch++) {
      const out = buf.getChannelData(ch);
      for (let i = 0; i < frames; i++) {
        out[i] = raw[i * CHANNELS + ch] / 32768;
      }
    }

    const src = audioCtx.createBufferSource();
    src.buffer = buf;
    src.connect(audioCtx.destination);

    const now = audioCtx.currentTime;
    if (nextTime < now) nextTime = now;
    src.start(nextTime);
    nextTime += buf.duration;
  };

  audioWs.onerror = () => { stopAudio(); };
  audioWs.onclose = () => { audioWs = null; };
}

export function stopAudio() {
  if (audioWs) {
    audioWs.close();
    audioWs = null;
  }
  if (audioCtx) {
    audioCtx.close().catch(() => { });
    audioCtx = null;
  }
}

export function toggleAudio() {
  audioEnabled = !audioEnabled;
  const btn = el('btn-audio');
  if (audioEnabled) {
    btn.classList.add('active');
    startAudio();
  } else {
    btn.classList.remove('active');
    stopAudio();
  }
}
