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

class Web2Local {
  constructor(port = 7878) {
    this.base = `http://127.0.0.1:${port}`;
  }

  async status() {
    const response = await fetch(`${this.base}/status`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  }

  async requestAccess() {
    const response = await fetch(`${this.base}/handshake`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ origin: window.location.origin })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }

  async run(command, args = []) {
    const response = await fetch(`${this.base}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command, args })
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
    return data;
  }
}

const padGrid = document.querySelector('#padGrid');
const title = document.querySelector('#modeTitle');
const description = document.querySelector('#modeDescription');
const base = document.querySelector('#modeBase');
const chord = document.querySelector('#modeChord');
const action = document.querySelector('#modeAction');
const tabs = [...document.querySelectorAll('.mode-tab')];
const runnerOutput = document.querySelector('#runnerOutput code');
const localPath = document.querySelector('#localPath');
const w2l = new Web2Local();

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

function setRunnerOutput(text) {
  if (runnerOutput) runnerOutput.textContent = text;
}

function helperPath() {
  const path = localPath.value.trim().replace(/\/+$/, '');
  return `${path}/tools/web2local-minipad.sh`;
}

async function runHelper(actionName) {
  if (actionName === 'install-hud') {
    const ok = window.confirm('Run the local HUD installer through web2local?');
    if (!ok) return;
  }

  const command = helperPath();
  setRunnerOutput(`running: ${command} ${actionName}`);
  const result = await w2l.run(command, [actionName]);
  const output = [
    `$ ${command} ${actionName}`,
    '',
    result.stdout || '',
    result.stderr ? `stderr:\n${result.stderr}` : '',
    `exit_code: ${result.exit_code}`
  ].filter(Boolean).join('\n');
  setRunnerOutput(output);
}

document.querySelectorAll('[data-runner]').forEach((button) => {
  button.addEventListener('click', async () => {
    const actionName = button.dataset.runner;
    try {
      if (actionName === 'daemon') {
        setRunnerOutput('checking http://127.0.0.1:7878/status');
        const status = await w2l.status();
        setRunnerOutput(JSON.stringify(status, null, 2));
        return;
      }
      if (actionName === 'access') {
        setRunnerOutput(`requesting access for ${window.location.origin}`);
        const access = await w2l.requestAccess();
        setRunnerOutput(JSON.stringify(access, null, 2));
        return;
      }
      await runHelper(actionName);
    } catch (error) {
      setRunnerOutput([
        'web2local request failed.',
        '',
        String(error.message || error),
        '',
        'Start web2local locally and grant this site access.'
      ].join('\n'));
    }
  });
});

renderMode('apps');
