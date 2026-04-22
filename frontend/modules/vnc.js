/** @description VNC display management for the desktop viewer panel. */

import { el } from './utils.js';
import { currentSessionId } from './state.js';

export function getVncUrl(sessionId) {
  const host = window.location.hostname || 'localhost';
  if (sessionId) {
    return `http://${host}:6080/vnc.html?resize=scale&autoconnect=true&reconnect=1&reconnect_delay=3000&path=websockify/?token=${sessionId}`;
  }
  return `http://${host}:6080/vnc.html?resize=scale&autoconnect=true`;
}

export function showVncFrame() {
  const frame = el('vnc-frame');
  const targetUrl = getVncUrl(currentSessionId);

  if (frame.style.display === 'block' && frame.src === targetUrl) return;

  frame.src = '';
  frame.style.display = 'block';
  el('vnc-placeholder').style.display = 'none';
  setTimeout(() => { frame.src = targetUrl; }, 200);
}

export function showVncPlaceholder(msg) {
  el('vnc-frame').src = '';
  el('vnc-frame').style.display = 'none';
  const ph = el('vnc-placeholder');
  ph.innerHTML = `<div class="vnc-placeholder-inner"><div class="vnc-placeholder-title">${msg || 'No desktop active'}</div><div class="vnc-placeholder-hint">Open a session from the sidebar to view the remote desktop</div></div>`;
  ph.style.display = 'flex';
}
