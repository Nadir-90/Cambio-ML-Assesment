/** @description Session CRUD: list, open, create, and delete sessions. */

import { el, escHtml } from './utils.js';
import {
  API, currentSessionId, currentSessionStatus,
  setCurrentSessionId, setCurrentSessionStatus, setStreamingBubble, setFileTree,
} from './state.js';
import { showDialog } from './dialog.js';
import {
  appendMsg, setRunning, setChatSessionActive,
  renderMessage, connectSSE, closeEventSource,
} from './chat.js';
import { showVncFrame, showVncPlaceholder } from './vnc.js';
import { loadFiles, renderFileTree } from './files.js';

function relativeTime(dateStr) {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return mins + 'm ago';
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return hrs + 'h ago';
  return Math.floor(hrs / 24) + 'd ago';
}

function statusLabel(status) {
  const labels = { new: 'New', active: 'Active', running: 'Running', stopped: 'Stopped' };
  return labels[status] || status;
}

export async function loadSessions() {
  try {
    const res = await fetch(`${API}/api/v1/sessions`);
    if (!res.ok) return;
    const list = await res.json();
    const cont = el('session-list');
    cont.innerHTML = '';

    if (!list.length) {
      cont.innerHTML = `
        <div class="empty-state">
          <strong>No sessions yet</strong>
          Click "New Session" to get started
        </div>`;
      return;
    }

    list.forEach(s => {
      const div = document.createElement('div');
      div.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
      div.dataset.id = s.id;
      div.setAttribute('role', 'listitem');
      div.innerHTML = `
        <div class="s-row">
          <div class="s-title">${escHtml(s.title || 'New Session')}</div>
          <button class="s-delete" title="Delete session" aria-label="Delete session">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
              <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
          </button>
        </div>
        <div class="s-meta">
          <span class="status-dot status-dot-${s.status}"></span>
          <span>${statusLabel(s.status)}</span>
          <span class="s-time">${relativeTime(s.updated_at)}</span>
        </div>
      `;
      div.addEventListener('click', (e) => {
        if (!e.target.closest('.s-delete')) openSession(s.id);
      });
      div.querySelector('.s-delete').addEventListener('click', (e) => {
        e.stopPropagation();
        deleteSession(s.id);
      });
      cont.appendChild(div);
    });

    if (currentSessionId) {
      const cur = list.find(s => s.id === currentSessionId);
      if (cur) el('chat-title-text').textContent = cur.title || 'New Session';
    }
  } catch {}
}

export async function openSession(sessionId) {
  if (currentSessionId === sessionId) {
    el('layout').classList.remove('sidebar-open');
    return;
  }

  el('layout').classList.remove('sidebar-open');

  try {
    await fetch(`${API}/api/v1/sessions/${sessionId}/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reset_display: false }),
    });
  } catch {
    appendMsg('msg-error', 'Failed to activate session.');
    return;
  }

  setCurrentSessionId(sessionId);
  document.querySelectorAll('.session-item').forEach(d =>
    d.classList.toggle('active', d.dataset.id === sessionId)
  );

  try {
    const res = await fetch(`${API}/api/v1/sessions/${sessionId}`);
    if (!res.ok) throw new Error();
    const session = await res.json();

    setCurrentSessionStatus(session.status);
    setStreamingBubble(null);
    el('chat-messages').innerHTML = '';
    el('chat-title-text').textContent = session.title || 'New Session';
    setChatSessionActive(true);
    el('msg-input').disabled = false;
    el('btn-send').disabled = false;

    try {
      const msgsRes = await fetch(`${API}/api/v1/sessions/${sessionId}/messages`);
      if (msgsRes.ok) {
        const messages = await msgsRes.json();
        messages.forEach(m => renderMessage(m));
      }
    } catch {}

    closeEventSource();
    setRunning(session.status === 'running');
    if (session.status === 'running') connectSSE(sessionId);

    showVncFrame();
    setFileTree({});
    loadFiles();
    await loadSessions();
  } catch {
    appendMsg('msg-error', 'Failed to load session.');
  }
}

export async function newSession() {
  try {
    const res = await fetch(`${API}/api/v1/sessions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || 'Failed to create session.');
    }
    const session = await res.json();

    await fetch(`${API}/api/v1/sessions/${session.id}/activate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reset_display: false }),
    });

    closeEventSource();
    setCurrentSessionId(session.id);
    setCurrentSessionStatus('active');
    setStreamingBubble(null);
    el('chat-messages').innerHTML = '';
    el('chat-title-text').textContent = session.title || 'New Session';
    setChatSessionActive(true);
    el('msg-input').disabled = false;
    el('btn-send').disabled = false;
    setRunning(false);
    showVncFrame();
    setFileTree({});
    loadFiles();
    await loadSessions();
  } catch (e) {
    appendMsg('msg-error', e.message || 'Failed to create session.');
  }
}

export async function deleteSession(sessionId) {
  const result = await showDialog({
    title: 'Delete Session',
    message: 'This will stop and remove the session container. All data in the session will be lost.',
    buttons: [
      { label: 'Delete', value: 'delete', style: 'primary' },
    ],
  });
  if (result.action === 'cancel') return;

  try {
    const res = await fetch(`${API}/api/v1/sessions/${sessionId}`, { method: 'DELETE' });
    if (!res.ok) throw new Error();

    if (currentSessionId === sessionId) {
      setCurrentSessionId(null);
      setCurrentSessionStatus(null);
      closeEventSource();
      el('chat-messages').innerHTML = '';
      el('chat-title-text').textContent = '';
      el('btn-stop').style.display = 'none';
      el('msg-input').disabled = true;
      el('btn-send').disabled = true;
      setChatSessionActive(false);
      showVncPlaceholder();
      setFileTree({});
      renderFileTree();
    }
    await loadSessions();
  } catch {
    appendMsg('msg-error', 'Failed to delete session.');
  }
}
