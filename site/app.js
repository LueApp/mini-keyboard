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

// ── web2local console ──────────────────────────────────────────────────────
// Detection-driven: probe the daemon, reflect state in a status chip, and gate
// the action buttons until it is reachable. Each action runs ONE named helper
// action — never free-form shell input — and web2local prompts for approval.
const w2lStatus = document.querySelector('#w2lStatus');
const w2lMsg = document.querySelector('#w2lMsg');
const w2lPortInput = document.querySelector('#w2lPort');
const w2lCheckBtn = document.querySelector('#w2lCheck');
const w2lGet = document.querySelector('#w2lGet');
const runnerOutput = document.querySelector('#runnerOutput');
const localPath = document.querySelector('#localPath');
const needsW2l = [...document.querySelectorAll('[data-needs-w2l]')];

const STORE = { port: 'minipad.w2lPort', path: 'minipad.localPath' };
const CONFIRMS = {
  'install-hud': 'Install the mini-keyboard HUD on this machine through web2local?',
  'uninstall-hud': 'Uninstall the mini-keyboard HUD from this machine through web2local?'
};

function store(key, value) { try { localStorage.setItem(key, value); } catch { /* ignore */ } }
function recall(key) { try { return localStorage.getItem(key); } catch { return null; } }

function w2lPort() {
  const n = parseInt(w2lPortInput && w2lPortInput.value, 10);
  return Number.isFinite(n) && n > 0 ? n : 7878;
}

function client() {
  return window.Web2Local ? new window.Web2Local(w2lPort()) : null;
}

function setBadge(state, text) {
  if (w2lStatus) { w2lStatus.dataset.state = state; w2lStatus.textContent = text; }
}

function setMsg(html) {
  if (w2lMsg) w2lMsg.innerHTML = html;
}

function setActionsEnabled(enabled) {
  needsW2l.forEach((button) => { button.disabled = !enabled; });
}

function showOutput(text) {
  if (!runnerOutput) return;
  runnerOutput.hidden = false;
  runnerOutput.textContent = text;
}

function helperPath() {
  const path = localPath.value.trim().replace(/\/+$/, '');
  return `${path}/tools/web2local-minipad.sh`;
}

// Probe the daemon and drive the whole card's state. Never throws.
async function checkDaemon() {
  const w2l = client();
  if (!w2l) {
    setBadge('absent', 'client failed');
    setActionsEnabled(false);
    setMsg('The web2local client library failed to load. Reload the page.');
    return false;
  }
  setBadge('checking', 'checking…');
  const port = w2lPort();
  const up = await w2l.isRunning();
  if (up) {
    setBadge('present', 'detected');
    setActionsEnabled(true);
    if (w2lGet) w2lGet.hidden = true;
    try { await w2l.addToGraylist(window.location.origin); } catch { /* approval still per-action */ }
    setMsg(`Detected on port <strong>${port}</strong>. Pick an action — web2local asks you to approve each one.`);
  } else {
    setBadge('absent', 'not running');
    setActionsEnabled(false);
    if (w2lGet) w2lGet.hidden = false;
    setMsg(`Not detected on port <strong>${port}</strong>. Start web2local locally, then press <strong>Check</strong>.`);
  }
  return up;
}

async function runHelper(actionName) {
  const confirmMsg = CONFIRMS[actionName];
  if (confirmMsg && !window.confirm(confirmMsg)) return;
  const command = helperPath();
  setBadge('working', 'working…');
  showOutput(`$ ${command} ${actionName}\n\nrunning…`);
  try {
    const result = await client().run(command, [actionName]);
    showOutput([
      `$ ${command} ${actionName}`,
      '',
      result.stdout || '',
      result.stderr ? `stderr:\n${result.stderr}` : '',
      `exit_code: ${result.exit_code}`
    ].filter(Boolean).join('\n'));
  } finally {
    setBadge('present', 'detected');
  }
}

async function handleRunner(actionName) {
  if (!window.Web2Local) {
    showOutput('web2local client library failed to load. Reload the page.');
    return;
  }
  try {
    if (actionName === 'access') {
      setBadge('working', 'working…');
      showOutput(`requesting access for ${window.location.origin}…`);
      const access = await client().requestAccess();
      showOutput(JSON.stringify(access, null, 2));
      await checkDaemon();
      return;
    }
    await runHelper(actionName);
  } catch (error) {
    showOutput([
      'web2local request failed.',
      '',
      String((error && error.message) || error),
      '',
      'Make sure web2local is running and you approved this action.'
    ].join('\n'));
    await checkDaemon();
  }
}

document.querySelectorAll('[data-runner]').forEach((button) => {
  button.addEventListener('click', () => handleRunner(button.dataset.runner));
});
if (w2lCheckBtn) w2lCheckBtn.addEventListener('click', () => checkDaemon());
if (w2lPortInput) w2lPortInput.addEventListener('change', () => { store(STORE.port, w2lPortInput.value); checkDaemon(); });
if (localPath) localPath.addEventListener('change', () => store(STORE.path, localPath.value));

// Restore remembered port / checkout path.
const savedPort = recall(STORE.port);
if (savedPort && w2lPortInput) w2lPortInput.value = savedPort;
const savedPath = recall(STORE.path);
if (savedPath && localPath) localPath.value = savedPath;

// ── Boot ───────────────────────────────────────────────────────────────────
renderMode('apps');
checkDaemon();
