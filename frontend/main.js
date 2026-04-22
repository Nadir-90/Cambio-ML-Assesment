/** @description Application entry point: wires modules and registers event listeners. */

import { el } from './modules/utils.js';
import { currentSessionId, currentSessionStatus } from './modules/state.js';
import { sendMessage, stopTask, setOnSessionsChanged } from './modules/chat.js';
import { loadSessions, newSession } from './modules/session.js';
import { toggleAudio } from './modules/audio.js';
import { refreshFiles, setupFileDrop } from './modules/files.js';

setOnSessionsChanged(loadSessions);

el('btn-sidebar-toggle').addEventListener('click', () => {
  el('layout').classList.toggle('sidebar-open');
});

el('btn-new').addEventListener('click', newSession);
el('btn-send').addEventListener('click', sendMessage);
el('btn-stop').addEventListener('click', stopTask);
el('btn-audio').addEventListener('click', toggleAudio);
el('btn-refresh-files').addEventListener('click', refreshFiles);

el('msg-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

el('msg-input').addEventListener('input', (e) => {
  const ta = e.target;
  ta.style.height = '80px';
  ta.style.height = Math.min(ta.scrollHeight, 240) + 'px';
});

window.addEventListener('beforeunload', (e) => {
  if (currentSessionId && currentSessionStatus === 'running') {
    e.preventDefault();
  }
});

setupFileDrop();
setInterval(loadSessions, 30_000);
loadSessions();
