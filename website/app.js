const modes = {
  apps: {
    title: 'apps mode',
    description: 'Clipboard, tab, save, find, close, and window-switching shortcuts.',
    base: 'Yes',
    chord: '1+3',
    action: 'clear()',
    keys: [
      ['1', 'Copy', 'C-c'], ['2', 'Paste', 'C-v'], ['3', 'Cut', 'C-x'],
      ['4', 'Undo', 'C-z'], ['5', 'Redo', 'C-S-z'], ['6', 'Save', 'C-s'],
      ['7', 'All', 'C-a'], ['8', 'Find', 'C-f'], ['9', 'Close', 'C-w'],
      ['0', 'Switch', 'A-tab'], ['a', 'New tab', 'C-t'], ['b', 'Reopen', 'C-S-t']
    ]
  },
  nav: {
    title: 'nav mode',
    description: 'Arrow keys, page movement, enter, tab, escape, and backspace.',
    base: 'No',
    chord: '4+6',
    action: 'swap(nav)',
    keys: [
      ['1', 'Home', 'home'], ['2', 'Up', 'up'], ['3', 'Page Up', 'pageup'],
      ['4', 'Left', 'left'], ['5', 'Enter', 'enter'], ['6', 'Right', 'right'],
      ['7', 'End', 'end'], ['8', 'Down', 'down'], ['9', 'Page Down', 'pagedown'],
      ['0', 'Esc', 'esc'], ['a', 'Tab', 'tab'], ['b', 'Backspace', 'backspace']
    ]
  },
  num: {
    title: 'num mode',
    description: 'Calculator-style number entry using digit-row keycodes, not keypad codes.',
    base: 'No',
    chord: '7+9',
    action: 'swap(num)',
    keys: [
      ['1', '7', '7'], ['2', '8', '8'], ['3', '9', '9'],
      ['4', '4', '4'], ['5', '5', '5'], ['6', '6', '6'],
      ['7', '1', '1'], ['8', '2', '2'], ['9', '3', '3'],
      ['0', '0', '0'], ['a', '.', '.'], ['b', 'Enter', 'enter']
    ]
  }
};

const padGrid = document.querySelector('#padGrid');
const title = document.querySelector('#modeTitle');
const description = document.querySelector('#modeDescription');
const base = document.querySelector('#modeBase');
const chord = document.querySelector('#modeChord');
const action = document.querySelector('#modeAction');
const tabs = [...document.querySelectorAll('.mode-tab')];

function renderMode(modeName) {
  const mode = modes[modeName];
  padGrid.innerHTML = mode.keys.map(([phys, label, value]) => `
    <div class="pad-key">
      <span class="phys">${phys}</span>
      <strong>${label}</strong>
      <span class="value">${value}</span>
    </div>
  `).join('');
  title.textContent = mode.title;
  description.textContent = mode.description;
  base.textContent = mode.base;
  chord.textContent = mode.chord;
  action.textContent = mode.action;
  tabs.forEach((tab) => {
    const active = tab.dataset.mode === modeName;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
  });
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => renderMode(tab.dataset.mode));
});

document.querySelectorAll('.copy-button').forEach((button) => {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.textContent = 'Copied';
      setTimeout(() => {
        button.textContent = 'Copy';
      }, 1400);
    } catch {
      button.textContent = 'Select';
      setTimeout(() => {
        button.textContent = 'Copy';
      }, 1400);
    }
  });
});

renderMode('apps');
