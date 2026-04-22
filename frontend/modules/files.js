/** @description File browser with drag-and-drop upload support (files and folders). */

import { el, escHtml, formatSize } from './utils.js';
import { API, currentSessionId, fileTree, setFileTree } from './state.js';
import { appendMsg } from './chat.js';

export function fileSessionParam() {
  return currentSessionId ? `&session_id=${currentSessionId}` : '';
}

export async function loadFiles(path) {
  const p = path || '.';
  if (!el('file-list') || !currentSessionId) return;
  try {
    const res = await fetch(`${API}/api/v1/files?path=${encodeURIComponent(p)}${fileSessionParam()}`);
    if (!res.ok) return;
    const data = await res.json();
    fileTree[p] = { loaded: true, expanded: true, entries: data.entries };
    renderFileTree();
  } catch {}
}

export function refreshFiles() {
  setFileTree({});
  loadFiles('.');
}

export function toggleFolder(path) {
  const node = fileTree[path];
  if (node && node.loaded) {
    node.expanded = !node.expanded;
    renderFileTree();
  } else {
    loadFiles(path);
  }
}

export function renderFileTree() {
  const list = el('file-list');
  const zone = el('file-drop-zone');
  const uploadBtn = el('btn-upload');
  const refreshBtn = el('btn-refresh-files');
  if (!list) return;

  const hasSession = !!currentSessionId;
  if (uploadBtn) uploadBtn.disabled = !hasSession;
  if (refreshBtn) refreshBtn.disabled = !hasSession;

  const root = fileTree['.'];
  const hasFiles = root && root.entries && root.entries.length;
  if (zone) zone.style.display = (hasSession && !hasFiles) ? '' : 'none';
  if (!hasFiles) {
    list.innerHTML = hasSession ? '<div class="file-empty">No files</div>' : '';
    return;
  }
  list.innerHTML = buildTreeHtml('.', 0);
}

function fileActions(fullPath) {
  return `<span class="file-actions">
    <button class="file-btn file-dl" data-path="${escHtml(fullPath)}" title="Download">\u2B07</button>
    <button class="file-btn file-rm" data-path="${escHtml(fullPath)}" title="Delete">\u{1F5D1}</button>
  </span>`;
}

function buildTreeHtml(parentPath, depth) {
  const node = fileTree[parentPath];
  if (!node || !node.entries) return '';
  return node.entries.map(e => {
    const fullPath = parentPath === '.' ? e.name : `${parentPath}/${e.name}`;
    const pad = depth * 16;
    if (e.type === 'dir') {
      const expanded = fileTree[fullPath]?.expanded;
      const arrow = expanded ? '\u25BE' : '\u25B8';
      let html = `<div class="file-entry file-dir" data-path="${escHtml(fullPath)}" style="padding-left:${pad + 4}px">
        <span class="file-arrow">${arrow}</span>
        <span class="file-icon">\u{1F4C1}</span>
        <span class="file-name">${escHtml(e.name)}</span>
        ${fileActions(fullPath)}
      </div>`;
      if (expanded && fileTree[fullPath]) {
        html += buildTreeHtml(fullPath, depth + 1);
      }
      return html;
    }
    return `<div class="file-entry" style="padding-left:${pad + 4}px">
      <span class="file-arrow" style="visibility:hidden">\u25B8</span>
      <span class="file-icon">\u{1F4C4}</span>
      <span class="file-name">${escHtml(e.name)}</span>
      ${e.size != null ? `<span class="file-size">${formatSize(e.size)}</span>` : ''}
      ${fileActions(fullPath)}
    </div>`;
  }).join('');
}

async function deleteItem(path) {
  if (!currentSessionId) return;
  try {
    const url = `${API}/api/v1/files?path=${encodeURIComponent(path)}&session_id=${currentSessionId}`;
    const res = await fetch(url, { method: 'DELETE' });
    if (!res.ok) throw new Error();
    refreshFiles();
  } catch {
    appendMsg('msg-error', 'Failed to delete.');
  }
}

function downloadItem(path) {
  if (!currentSessionId) return;
  const url = `${API}/api/v1/files/download?path=${encodeURIComponent(path)}&session_id=${currentSessionId}`;
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  document.body.appendChild(a);
  a.click();
  a.remove();
}

async function readAllEntries(reader) {
  const all = [];
  let batch;
  do {
    batch = await new Promise(resolve => reader.readEntries(resolve));
    all.push(...batch);
  } while (batch.length > 0);
  return all;
}

async function collectDroppedFiles(dataTransfer) {
  const files = [];
  const paths = [];
  const items = [...dataTransfer.items];

  async function traverse(entry, basePath) {
    if (entry.isFile) {
      const file = await new Promise(resolve => entry.file(resolve));
      files.push(file);
      paths.push(basePath + entry.name);
    } else if (entry.isDirectory) {
      const reader = entry.createReader();
      const entries = await readAllEntries(reader);
      for (const child of entries) {
        await traverse(child, basePath + entry.name + '/');
      }
    }
  }

  const entries = items.map(i => i.webkitGetAsEntry?.()).filter(Boolean);
  if (entries.length) {
    for (const entry of entries) await traverse(entry, '');
    return { files, paths };
  }
  return null;
}

export async function uploadItems(files, paths) {
  if (!currentSessionId || !files.length) return;
  const form = new FormData();
  for (let i = 0; i < files.length; i++) {
    form.append('files', files[i]);
    form.append('paths', paths ? paths[i] : (files[i].webkitRelativePath || files[i].name));
  }
  try {
    const url = `${API}/api/v1/files/upload?session_id=${currentSessionId}`;
    const res = await fetch(url, { method: 'POST', body: form });
    if (!res.ok) throw new Error();
    refreshFiles();
  } catch {
    appendMsg('msg-error', 'Failed to upload.');
  }
}

async function handleDrop(dataTransfer) {
  const result = await collectDroppedFiles(dataTransfer);
  if (result && result.files.length) {
    uploadItems(result.files, result.paths);
  } else if (dataTransfer.files.length) {
    uploadItems(dataTransfer.files);
  }
}

function showUploadMenu(anchor) {
  const menu = el('upload-menu');
  if (!menu) return;
  const rect = anchor.getBoundingClientRect();
  menu.style.top = (rect.bottom + 4) + 'px';
  menu.style.right = (window.innerWidth - rect.right) + 'px';
  menu.classList.add('open');
}

function hideUploadMenu() {
  const menu = el('upload-menu');
  if (menu) menu.classList.remove('open');
}

export function setupFileDrop() {
  const zone = el('file-drop-zone');
  const fileInput = el('file-input');
  const folderInput = el('folder-input');
  const uploadBtn = el('btn-upload');
  const uploadMenu = el('upload-menu');
  const fileList = el('file-list');
  if (!fileInput) return;

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) uploadItems(fileInput.files);
    fileInput.value = '';
  });

  if (folderInput) {
    folderInput.addEventListener('change', () => {
      if (folderInput.files.length) uploadItems(folderInput.files);
      folderInput.value = '';
    });
  }

  if (uploadMenu) {
    uploadMenu.addEventListener('click', (e) => {
      const item = e.target.closest('.upload-menu-item');
      if (!item) return;
      hideUploadMenu();
      if (item.dataset.mode === 'folder' && folderInput) folderInput.click();
      else fileInput.click();
    });
    document.addEventListener('click', (e) => {
      if (!e.target.closest('.upload-menu') && !e.target.closest('#btn-upload')) hideUploadMenu();
    });
  }

  if (uploadBtn) {
    uploadBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      uploadMenu?.classList.contains('open') ? hideUploadMenu() : showUploadMenu(uploadBtn);
    });
  }

  if (zone) {
    zone.addEventListener('click', () => showUploadMenu(zone));
    zone.addEventListener('dragover', (e) => {
      e.preventDefault();
      zone.classList.add('drag-over');
    });
    zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
    zone.addEventListener('drop', (e) => {
      e.preventDefault();
      zone.classList.remove('drag-over');
      handleDrop(e.dataTransfer);
    });
  }

  if (fileList) {
    fileList.addEventListener('click', (e) => {
      const dlBtn = e.target.closest('.file-dl');
      if (dlBtn) { e.stopPropagation(); downloadItem(dlBtn.dataset.path); return; }
      const rmBtn = e.target.closest('.file-rm');
      if (rmBtn) { e.stopPropagation(); deleteItem(rmBtn.dataset.path); return; }
      const dir = e.target.closest('.file-dir');
      if (dir) toggleFolder(dir.dataset.path);
    });
    fileList.addEventListener('dragover', (e) => e.preventDefault());
    fileList.addEventListener('drop', (e) => {
      e.preventDefault();
      handleDrop(e.dataTransfer);
    });
  }
}
