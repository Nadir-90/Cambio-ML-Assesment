/** @description Chat messaging, SSE streaming, and event handling. */

import { el, escHtml, escHtmlNl, stripAnsi } from './utils.js';
import {
  API, currentSessionId, currentSessionStatus, currentEventSource,
  streamingBubble,
  setCurrentSessionStatus, setCurrentEventSource, setStreamingBubble,
} from './state.js';

let onSessionsChanged = null;

export function setOnSessionsChanged(fn) {
  onSessionsChanged = fn;
}

export function scrollChat() {
  const c = el('chat-messages');
  c.scrollTop = c.scrollHeight;
}

export function appendMsg(cls, html) {
  const div = document.createElement('div');
  div.className = `msg ${cls}`;
  div.innerHTML = html;
  el('chat-messages').appendChild(div);
  scrollChat();
  return div;
}

export function setRunning(running) {
  el('msg-input').disabled = running;
  el('btn-send').disabled = running;
  el('btn-stop').style.display = running ? 'inline-flex' : 'none';
}

export function setChatSessionActive(active) {
  const title = el('chat-panel-title');
  const placeholder = el('chat-placeholder');
  const messages = el('chat-messages');
  if (active) {
    title.classList.remove('hidden');
    placeholder.style.display = 'none';
    messages.style.display = 'flex';
  } else {
    title.classList.add('hidden');
    placeholder.style.display = 'flex';
    messages.style.display = 'none';
  }
}

export function renderMessage(m) {
  switch (m.message_type) {
    case 'text':
      if (m.role === 'user') {
        appendMsg('msg-user', escHtmlNl(m.content?.text || ''));
      } else {
        appendMsg('msg-assistant', escHtmlNl(m.content?.text || ''));
      }
      break;
    case 'tool_use': {
      let html = `<div class="tool-name">\u2699 ${escHtml(m.content?.name)}</div>`;
      if (m.content?.input && Object.keys(m.content.input).length) {
        html += `<div class="tool-output">${escHtml(JSON.stringify(m.content.input, null, 2))}</div>`;
      }
      appendMsg('msg-tool', html);
      break;
    }
    case 'tool_result': {
      let html = `<div class="tool-name">\u2714 Result</div>`;
      if (m.content?.output) html += `<div class="tool-output">${escHtmlNl(stripAnsi(m.content.output))}</div>`;
      if (m.content?.error) html += `<div class="tool-output" style="color:var(--error)">${escHtmlNl(stripAnsi(m.content.error))}</div>`;
      if (m.content?.screenshot) html += `<img src="data:image/png;base64,${m.content.screenshot}" alt="screenshot">`;
      appendMsg('msg-tool', html);
      break;
    }
  }
}

export function connectSSE(sessionId) {
  closeEventSource();
  const es = new EventSource(`${API}/api/v1/agent/${sessionId}/stream`);
  setCurrentEventSource(es);

  es.onmessage = (e) => {
    try { handleEvent(JSON.parse(e.data)); } catch { }
  };

  es.onerror = () => {
    es.close();
    setCurrentEventSource(null);
    if (currentSessionStatus === 'running') {
      appendMsg('msg-status', 'Connection lost. The task may still be running.');
    }
    setRunning(false);
    if (onSessionsChanged) onSessionsChanged();
  };
}

export function closeEventSource() {
  if (currentEventSource) {
    currentEventSource.close();
    setCurrentEventSource(null);
  }
}

export function handleEvent(event) {
  if (event.type !== 'text_chunk' && event.type !== 'heartbeat') {
    if (streamingBubble) streamingBubble.classList.remove('streaming');
    setStreamingBubble(null);
  }

  switch (event.type) {
    case 'connected':
      appendMsg('msg-status', '<span class="spinner"></span> Connected \u2014 waiting for agent\u2026');
      break;

    case 'user_message':
      appendMsg('msg-user', escHtmlNl(event.text));
      break;

    case 'text_chunk': {
      if (!streamingBubble) {
        const bubble = appendMsg('msg-assistant', '');
        bubble.classList.add('streaming');
        setStreamingBubble(bubble);
      }
      const span = document.createElement('span');
      span.innerHTML = escHtmlNl(event.text);
      streamingBubble.appendChild(span);
      scrollChat();
      break;
    }

    case 'tool_use': {
      let html = `<div class="tool-name">\u2699 ${escHtml(event.name)}</div>`;
      if (event.input && Object.keys(event.input).length) {
        html += `<div class="tool-output">${escHtml(JSON.stringify(event.input, null, 2))}</div>`;
      }
      appendMsg('msg-tool', html);
      break;
    }

    case 'tool_result': {
      let html = `<div class="tool-name">\u2714 Result</div>`;
      if (event.output) html += `<div class="tool-output">${escHtmlNl(stripAnsi(event.output))}</div>`;
      if (event.error) html += `<div class="tool-output" style="color:var(--error)">${escHtmlNl(stripAnsi(event.error))}</div>`;
      if (event.screenshot) html += `<img src="data:image/png;base64,${event.screenshot}" alt="screenshot">`;
      appendMsg('msg-tool', html);
      break;
    }

    case 'api_response':
      if (event.error) appendMsg('msg-error', `API error: ${escHtml(event.error)}`);
      break;

    case 'heartbeat':
      break;

    case 'completed':
      setCurrentSessionStatus('active');
      appendMsg('msg-status', '\u2713 Task completed.');
      setRunning(false);
      closeEventSource();
      if (onSessionsChanged) onSessionsChanged();
      break;

    case 'error':
      setCurrentSessionStatus('active');
      appendMsg('msg-error', `Error: ${escHtml(event.message || 'Unknown error')}`);
      setRunning(false);
      closeEventSource();
      if (onSessionsChanged) onSessionsChanged();
      break;

    case 'cancelled':
      setCurrentSessionStatus('active');
      appendMsg('msg-status', 'Task cancelled.');
      setRunning(false);
      closeEventSource();
      if (onSessionsChanged) onSessionsChanged();
      break;
  }
}

export async function sendMessage() {
  const input = el('msg-input');
  const text = input.value.trim();
  if (!text || !currentSessionId) return;

  input.value = '';
  input.style.height = '80px';
  setRunning(true);
  setCurrentSessionStatus('running');

  try {
    const res = await fetch(`${API}/api/v1/agent/${currentSessionId}/task`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text }),
    });
    if (!res.ok) throw new Error();
    connectSSE(currentSessionId);
  } catch {
    appendMsg('msg-error', 'Failed to submit task.');
    setRunning(false);
    setCurrentSessionStatus('active');
  }
}

export async function stopTask() {
  if (!currentSessionId) return;
  try {
    await fetch(`${API}/api/v1/agent/${currentSessionId}/stop`, { method: 'POST' });
  } catch { }
}
