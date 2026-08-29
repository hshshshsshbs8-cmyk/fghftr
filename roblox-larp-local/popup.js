const KEY = 'larplab_state';
const defaults = { enabled:true, robux:999999, username:'LarpPlayer', displayName:'Larp Player', premium:true, verified:false, followers:12345, inventory:[], equipped:[] };
chrome.storage.local.get(KEY).then(({[KEY]: saved}) => {
  const s = {...defaults, ...(saved || {})};
  robux.value = s.robux; username.value = s.username; displayName.value = s.displayName;
});
save.onclick = async () => {
  const current = (await chrome.storage.local.get(KEY))[KEY] || defaults;
  await chrome.storage.local.set({[KEY]: {...current, robux:Number(robux.value)||0, username:username.value||'LarpPlayer', displayName:displayName.value||'Larp Player'}});
  save.textContent = 'Saved ✓';
  setTimeout(() => save.textContent = 'Save local profile', 900);
};
