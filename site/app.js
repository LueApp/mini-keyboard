// mini-keyboard guide — page behaviour.
//
// Two independent pieces:
//   1. The mode workbench (pure client-side: render the three keyd layers).
//   2. The web2local launcher: call a NARROW, named local helper through the
//      web2local daemon (127.0.0.1:7878). The page only ever sends a fixed
//      action name to tools/web2local-minipad.sh — never free-form shell input.
//
// Depends on: web2local-client.js (window.Web2Local).

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

// ── Mode workbench ─────────────────────────────────────────────────────────
const padGrid = document.querySelector('#padGrid');
const modeTitle = document.querySelector('#modeTitle');
const modeDescription = document.querySelector('#modeDescription');
const modeBase = document.querySelector('#modeBase');
const modeChord = document.querySelector('#modeChord');
const modeAction = document.querySelector('#modeAction');
const tablist = document.querySelector('.mode-tabs');
const modePanel = document.querySelector('#modePanel');
const tabs = [...document.querySelectorAll('.mode-tab')];
const srStatus = document.querySelector('#srStatus');

function announce(message) {
  if (srStatus) srStatus.textContent = message;
}

function renderMode(modeName) {
  const mode = modes[modeName];
  if (!mode) return;
  padGrid.replaceChildren(...mode.keys.map(([phys, label, value]) => {
    const cell = document.createElement('div');
    cell.className = 'pad-key';
    const physEl = document.createElement('span');
    physEl.className = 'phys';
    physEl.textContent = phys;
    const labelEl = document.createElement('strong');
    labelEl.textContent = label;
    const valueEl = document.createElement('span');
    valueEl.className = 'value';
    valueEl.textContent = value;
    cell.append(physEl, labelEl, valueEl);
    return cell;
  }));
  modeTitle.textContent = mode.title;
  modeDescription.textContent = mode.description;
  modeBase.textContent = mode.base;
  modeChord.textContent = mode.chord;
  modeAction.textContent = mode.action;
  let activeTab = null;
  tabs.forEach((tab) => {
    const active = tab.dataset.mode === modeName;
    tab.classList.toggle('active', active);
    tab.setAttribute('aria-selected', String(active));
    tab.tabIndex = active ? 0 : -1; // roving tabindex
    if (active) activeTab = tab;
  });
  if (activeTab && modePanel) modePanel.setAttribute('aria-labelledby', activeTab.id);
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => renderMode(tab.dataset.mode));
});

// ARIA tablist keyboard pattern: arrows + Home/End move and focus selection.
if (tablist) {
  tablist.addEventListener('keydown', (event) => {
    const current = tabs.findIndex((t) => t.getAttribute('aria-selected') === 'true');
    let next;
    switch (event.key) {
      case 'ArrowRight':
      case 'ArrowDown': next = current + 1; break;
      case 'ArrowLeft':
      case 'ArrowUp': next = current - 1; break;
      case 'Home': next = 0; break;
      case 'End': next = tabs.length - 1; break;
      default: return;
    }
    event.preventDefault();
    const target = tabs[(next + tabs.length) % tabs.length];
    renderMode(target.dataset.mode);
    target.focus();
  });
}

// ── Copy buttons ───────────────────────────────────────────────────────────
document.querySelectorAll('.copy-button').forEach((button) => {
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      button.textContent = 'Copied';
      announce('Command copied to clipboard.');
    } catch {
      button.textContent = 'Select';
      announce('Copy failed — select the command and copy it manually.');
    }
    setTimeout(() => { button.textContent = 'Copy'; }, 1400);
  });
});

// ── web2local launcher ─────────────────────────────────────────────────────
const runnerOutput = document.querySelector('#runnerOutput code');
const runnerStatus = document.querySelector('#runnerStatus');
const localPath = document.querySelector('#localPath');
const needsW2l = [...document.querySelectorAll('[data-needs-w2l]')];
const w2l = window.Web2Local ? new window.Web2Local() : null;

const CONFIRMS = {
  'install-hud': 'Install the mini-keyboard HUD on this machine through web2local?',
  'uninstall-hud': 'Uninstall the mini-keyboard HUD from this machine through web2local?'
};

function setOutput(text) {
  if (runnerOutput) runnerOutput.textContent = text;
}

function setStatus(text) {
  if (runnerStatus) runnerStatus.textContent = `web2local status: ${text}`;
}

function setHelperEnabled(enabled) {
  needsW2l.forEach((button) => { button.disabled = !enabled; });
}

function helperPath() {
  const path = localPath.value.trim().replace(/\/+$/, '');
  return `${path}/tools/web2local-minipad.sh`;
}

// Passive check: is the daemon reachable? Updates the status line and gates the
// helper buttons. Never throws — a missing daemon is the normal first state.
async function refreshDaemon() {
  if (!w2l) {
    setStatus('client library failed to load.');
    setHelperEnabled(false);
    return false;
  }
  const up = await w2l.isRunning();
  if (up) {
    setStatus('running on 127.0.0.1:7878.');
  } else {
    setStatus('not reachable — start web2local locally, then Request access.');
  }
  setHelperEnabled(up);
  return up;
}

async function runHelper(actionName) {
  const confirmMsg = CONFIRMS[actionName];
  if (confirmMsg && !window.confirm(confirmMsg)) return;

  const command = helperPath();
  setOutput(`running: ${command} ${actionName}`);
  const result = await w2l.run(command, [actionName]);
  setOutput([
    `$ ${command} ${actionName}`,
    '',
    result.stdout || '',
    result.stderr ? `stderr:\n${result.stderr}` : '',
    `exit_code: ${result.exit_code}`
  ].filter(Boolean).join('\n'));
}

async function handleRunner(actionName) {
  if (!w2l) {
    setOutput('web2local client library failed to load. Reload the page.');
    return;
  }
  try {
    if (actionName === 'daemon') {
      setOutput('checking http://127.0.0.1:7878/status');
      const up = await refreshDaemon();
      if (up) setOutput(JSON.stringify(await w2l.status(), null, 2));
      else setOutput('web2local is not reachable on 127.0.0.1:7878.\nStart it locally and try again.');
      return;
    }
    if (actionName === 'access') {
      setOutput(`requesting access for ${window.location.origin}`);
      const access = await w2l.requestAccess();
      setOutput(JSON.stringify(access, null, 2));
      await refreshDaemon();
      return;
    }
    await runHelper(actionName);
  } catch (error) {
    setOutput([
      'web2local request failed.',
      '',
      String((error && error.message) || error),
      '',
      'Start web2local locally and grant this site access (Request access).'
    ].join('\n'));
  }
}

document.querySelectorAll('[data-runner]').forEach((button) => {
  button.addEventListener('click', () => handleRunner(button.dataset.runner));
});

// ── Boot ───────────────────────────────────────────────────────────────────
renderMode('apps');
refreshDaemon();
