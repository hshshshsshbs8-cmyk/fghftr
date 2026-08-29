(() => {
  const KEY = 'larplab_state';
  const defaults = {
    enabled: true,
    robux: 999999,
    username: 'LarpPlayer',
    displayName: 'Larp Player',
    premium: true,
    verified: false,
    followers: 12345,
    inventory: [],
    equipped: []
  };

  let state = { ...defaults };
  chrome.storage.local.get(KEY).then(({ [KEY]: saved }) => {
    state = { ...defaults, ...(saved || {}) };
    render();
  });

  const badge = 'data-larplab';

  function replaceText(root, values) {
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
      if (node.parentElement?.closest(`[${badge}]`)) continue;
      let text = node.nodeValue || '';
      for (const [needle, value] of values) {
        if (needle && text.includes(needle)) text = text.split(needle).join(String(value));
      }
      node.nodeValue = text;
    }
  }

  function render() {
    if (!state.enabled) return;
    replaceText(document.body, [
      ['999999', state.robux],
      ['LarpPlayer', state.username],
      ['Larp Player', state.displayName]
    ]);

    let panel = document.getElementById('larplab-panel');
    if (!panel) {
      panel = document.createElement('aside');
      panel.id = 'larplab-panel';
      panel.setAttribute(badge, '1');
      panel.style.cssText = 'position:fixed;right:16px;bottom:16px;z-index:2147483647;width:280px;padding:16px;border-radius:14px;background:#18181b;color:#fff;font:14px system-ui;box-shadow:0 12px 40px #0008;border:1px solid #3f3f46';
      document.body.appendChild(panel);
    }
    panel.innerHTML = `<b style="font-size:16px">LarpLab</b><div style="opacity:.7;margin:4px 0 12px">Local-only simulator</div><div>💰 ${state.robux.toLocaleString()} Robux</div><div>👤 ${escapeHtml(state.displayName)} (@${escapeHtml(state.username)})</div><div>💎 Premium: ${state.premium ? 'ON' : 'OFF'}</div><div>🎒 Simulated items: ${state.inventory.length}</div>`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }

  const observer = new MutationObserver(() => {
    clearTimeout(observer.timer);
    observer.timer = setTimeout(render, 80);
  });
  observer.observe(document.documentElement, { childList: true, subtree: true });
})();
