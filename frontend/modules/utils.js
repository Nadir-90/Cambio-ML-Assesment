/** @description DOM helpers, HTML escaping, and formatting utilities. */

export function el(id) {
  return document.getElementById(id);
}

export function escHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

export function escHtmlNl(str) {
  return escHtml(str).replace(/\n/g, '<br>');
}

export function stripAnsi(str) {
  return String(str ?? '').replace(/\x1b\[[0-9;]*[a-zA-Z]/g, '');
}

export function statusBadge(status) {
  return `<span class="status-badge status-${status}">${status}</span>`;
}

export function formatSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}
