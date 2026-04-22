/** @description Modal dialog with optional text input and validation. */

import { el } from './utils.js';

export function showDialog({ title, message, buttons, input }) {
  return new Promise((resolve) => {
    el('modal-title').textContent = title;
    el('modal-message').textContent = message;

    let existingInput = el('modal-overlay').querySelector('.modal-input-wrap');
    if (existingInput) existingInput.remove();

    let inputEl = null;
    let errorEl = null;

    if (input) {
      const wrap = document.createElement('div');
      wrap.className = 'modal-input-wrap';

      inputEl = document.createElement('input');
      inputEl.type = 'text';
      inputEl.className = 'modal-input';
      inputEl.placeholder = input.placeholder || '';
      if (input.maxLength) inputEl.maxLength = input.maxLength;
      if (input.value) inputEl.value = input.value;

      errorEl = document.createElement('div');
      errorEl.className = 'modal-input-error';

      wrap.appendChild(inputEl);
      wrap.appendChild(errorEl);

      el('modal-buttons').parentNode.insertBefore(wrap, el('modal-buttons'));

      setTimeout(() => inputEl.focus(), 50);
    }

    const container = el('modal-buttons');
    container.innerHTML = '';

    const finish = (value) => {
      el('modal-overlay').style.display = 'none';
      resolve({ action: value, inputValue: inputEl ? inputEl.value.trim() : '' });
    };

    buttons.forEach((btn) => {
      const b = document.createElement('button');
      b.className = `modal-btn ${btn.style || ''}`;
      b.textContent = btn.label;
      b.addEventListener('click', () => {
        if (btn.requiresInput && inputEl) {
          const val = inputEl.value.trim();
          if (!val) {
            errorEl.textContent = 'Username is required.';
            inputEl.classList.add('error');
            inputEl.focus();
            return;
          }
          if (!/^[a-z][a-z0-9_-]{2,31}$/.test(val)) {
            errorEl.textContent = 'Must be 3-32 chars, start with lowercase letter, only a-z 0-9 _ -';
            inputEl.classList.add('error');
            inputEl.focus();
            return;
          }
        }
        finish(btn.value);
      });
      container.appendChild(b);
    });

    if (inputEl) {
      inputEl.addEventListener('input', () => {
        errorEl.textContent = '';
        inputEl.classList.remove('error');
      });
      inputEl.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
          const target = buttons.find(b => b.requiresInput) || buttons[0];
          if (target) {
            container.querySelector('.modal-btn').click();
          }
        }
      });
    }

    const closeBtn = el('modal-close');
    const onClose = () => {
      el('modal-overlay').style.display = 'none';
      closeBtn.removeEventListener('click', onClose);
      resolve({ action: 'cancel', inputValue: '' });
    };
    closeBtn.addEventListener('click', onClose);

    el('modal-overlay').style.display = 'flex';
  });
}

export async function askForUsername(prefill) {
  const result = await showDialog({
    title: 'Create User',
    message: 'Enter a username for this session (lowercase, 3-32 chars):',
    input: { placeholder: 'e.g. alice', maxLength: 32, value: prefill || '' },
    buttons: [
      { label: 'Create', value: 'create', style: 'primary', requiresInput: true },
    ],
  });
  if (result.action === 'cancel') return null;
  return result.inputValue;
}
