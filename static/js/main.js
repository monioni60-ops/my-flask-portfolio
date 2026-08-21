(function () {
  "use strict";

  /* ---------- THEME ---------- */
  const root = document.documentElement;
  const themeToggle = document.getElementById('themeToggle');
  function setTheme(t) {
    root.setAttribute('data-theme', t);
    try { localStorage.setItem('onni-theme', t); } catch (e) {}
  }
  let saved = null;
  try { saved = localStorage.getItem('onni-theme'); } catch (e) {}
  if (saved) { setTheme(saved); }
  else if (window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) { setTheme('light'); }
  if (themeToggle) {
    themeToggle.addEventListener('click', () => {
      const cur = root.getAttribute('data-theme');
      setTheme(cur === 'dark' ? 'light' : 'dark');
    });
  }

  /* ---------- TOAST ---------- */
  const toast = document.getElementById('toast');
  const toastText = document.getElementById('toastText');
  let toastTimer = null;
  window.showToast = function (msg) {
    if (!toast) return;
    toastText.textContent = msg;
    toast.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove('show'), 2600);
  };

  /* ---------- CLIPBOARD HELPER ---------- */
  window.copyText = function (text) {
    return new Promise((resolve) => {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(() => resolve(true)).catch(fallbackCopy);
      } else { fallbackCopy(); }
      function fallbackCopy() {
        try {
          const ta = document.createElement('textarea');
          ta.value = text;
          ta.style.position = 'fixed';
          ta.style.opacity = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          resolve(true);
        } catch (e) { resolve(false); }
      }
    });
  };

  /* ---------- DISCORD COPY CARD ---------- */
  const copyCard = document.getElementById('copyCard');
  if (copyCard) {
    copyCard.addEventListener('click', async () => {
      const ok = await window.copyText('ONNI_MONNI');
      const copyCheck = document.getElementById('copyCheck');
      if (copyCheck) {
        copyCheck.classList.add('show');
        setTimeout(() => copyCheck.classList.remove('show'), 2200);
      }
      window.showToast(ok ? 'Ник скопирован в буфер обмена' : 'Не удалось скопировать: ONNI_MONNI');
    });
  }

  /* ---------- SHARE BUTTON ---------- */
  const shareBtn = document.getElementById('shareBtn');
  if (shareBtn) {
    shareBtn.addEventListener('click', async () => {
      const url = window.location.href;
      const ok = await window.copyText(url);
      window.showToast(ok ? 'Ссылка на сайт скопирована!' : 'Скопируйте вручную из адресной строки');
    });
  }

  /* ---------- QR POPOVER ---------- */
  const qrBtn = document.getElementById('qrBtn');
  const qrPopover = document.getElementById('qrPopover');
  if (qrBtn && qrPopover) {
    qrBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      qrPopover.classList.toggle('show');
    });
    document.addEventListener('click', (e) => {
      if (!qrPopover.contains(e.target) && e.target !== qrBtn && !qrBtn.contains(e.target)) {
        qrPopover.classList.remove('show');
      }
    });
  }

  /* ---------- FILTER BAR (index page) ---------- */
  const filterBar = document.getElementById('filterBar');
  if (filterBar) {
    filterBar.addEventListener('click', (e) => {
      const btn = e.target.closest('.filter-btn');
      if (!btn) return;
      window.location.href = btn.dataset.href;
    });
  }

  /* ---------- LIKE BUTTON (AJAX) ---------- */
  const likeBtn = document.getElementById('likeBtn');
  if (likeBtn) {
    likeBtn.addEventListener('click', async () => {
      if (likeBtn.dataset.authRequired === '1') {
        window.showToast('Зарегистрируйтесь, чтобы ставить лайки');
        return;
      }
      const url = likeBtn.dataset.url;
      try {
        const res = await fetch(url, {
          method: 'POST',
          headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
        const data = await res.json();
        if (data.ok) {
          likeBtn.classList.toggle('liked', data.liked);
          likeBtn.classList.remove('bump');
          void likeBtn.offsetWidth;
          likeBtn.classList.add('bump');
          const countEl = document.getElementById('likeCount');
          if (countEl) countEl.textContent = data.like_count;
        }
      } catch (err) {
        window.showToast('Ошибка сети. Попробуйте ещё раз.');
      }
    });
  }

  /* ---------- FLASH AUTO-HIDE ---------- */
  document.querySelectorAll('.flash').forEach((el) => {
    setTimeout(() => { el.style.transition = 'opacity .5s ease'; el.style.opacity = '0'; }, 4200);
  });

})();
