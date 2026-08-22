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

  /* ---------- LIKE BUTTON (AJAX, work.html standalone page) ---------- */
  const likeBtn = document.getElementById('likeBtn');
  if (likeBtn) {
    likeBtn.addEventListener('click', async () => {
      if (likeBtn.dataset.authRequired === '1') {
        window.showToast('Зарегистрируйтесь, чтобы ставить лайки');
        return;
      }
      const url = likeBtn.dataset.url;
      try {
        const res = await fetch(url, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
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

  /* =========================================================
     LIGHTBOX — fullscreen work viewer with keyboard nav,
     inline like + comments, loaded via /api/work/<id>
     ========================================================= */
  const overlay = document.getElementById('lightboxOverlay');
  if (overlay) {
    const isAuth = overlay.dataset.authenticated === '1';
    const isAdmin = overlay.dataset.isAdmin === '1';
    const panel = document.getElementById('lightboxPanel');
    const mediaImg = document.getElementById('lightboxImg');
    const closeBtn = document.getElementById('lightboxClose');
    const prevBtn = document.getElementById('lightboxPrev');
    const nextBtn = document.getElementById('lightboxNext');

    let order = [];
    let currentIndex = -1;

    function collectOrder() {
      order = Array.from(document.querySelectorAll('.card[data-work-id]')).map(
        (el) => parseInt(el.dataset.workId, 10)
      );
    }

    function escapeHtml(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }

    function renderComment(c) {
      return `
        <div class="comment-item">
          <div class="avatar">${escapeHtml(c.author[0].toUpperCase())}</div>
          <div class="comment-body">
            <div class="comment-item-head">
              <span class="comment-author">${escapeHtml(c.author)}</span>
              <span class="comment-date">${escapeHtml(c.date)}</span>
            </div>
            <div class="comment-text">${escapeHtml(c.text)}</div>
            ${c.can_delete ? `<button class="comment-admin-del" data-comment-id="${c.id}">Удалить</button>` : ''}
          </div>
        </div>`;
    }

    function renderWork(work) {
      mediaImg.src = work.image_src;
      mediaImg.alt = work.title;

      const commentsHtml = work.comments.length
        ? work.comments.map(renderComment).join('')
        : '<p class="empty-note">Комментариев пока нет. Будьте первым!</p>';

      const authBanner = !isAuth ? `
        <div class="auth-banner" style="margin-top:18px;">
          <div><p>Зарегистрируйтесь, чтобы лайкать и комментировать 🎨</p></div>
          <a class="btn btn-primary btn-sm" href="/register">Зарегистрироваться</a>
        </div>` : '';

      const commentForm = isAuth ? `
        <form class="comment-form" id="lightboxCommentForm" style="margin-top:18px;">
          <textarea name="text" placeholder="Напишите комментарий..." maxlength="1000" required></textarea>
          <button type="submit" class="btn btn-primary btn-sm">Отправить</button>
        </form>` : '';

      panel.innerHTML = `
        <div class="lightbox-tag">${escapeHtml(work.category_label)}</div>
        <div class="lightbox-title">${escapeHtml(work.title)}</div>
        <div class="lightbox-stats">
          <span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7Z"/><circle cx="12" cy="12" r="3"/></svg> ${work.views} просмотров</span>
          <span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg> ${work.comment_count} комментариев</span>
          <span><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8 7V3m8 4V3M3 11h18M5 21h14a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2Z"/></svg> ${work.date}</span>
        </div>
        ${work.description ? `<p class="lightbox-desc">${escapeHtml(work.description)}</p>` : ''}
        <button class="like-btn lightbox-like ${work.is_liked ? 'liked' : ''}" id="lightboxLikeBtn" data-auth-required="${isAuth ? '0' : '1'}">
          <svg viewBox="0 0 24 24" fill="${work.is_liked ? 'currentColor' : 'none'}" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 21s-6.7-4.35-9.3-8.1C.8 10.1 1.4 6.6 4.3 5c2.2-1.2 4.7-.6 6 1.2l1.7 2.1 1.7-2.1c1.3-1.8 3.8-2.4 6-1.2 2.9 1.6 3.5 5.1 1.6 7.9C18.7 16.65 12 21 12 21Z"/></svg>
          <span id="lightboxLikeCount">${work.like_count}</span>
        </button>
        ${authBanner}
        <div class="lightbox-comments">
          <h4>Комментарии (<span id="lightboxCommentCount">${work.comment_count}</span>)</h4>
          ${commentForm}
          <div class="comment-list" id="lightboxCommentList">${commentsHtml}</div>
        </div>
      `;

      const likeBtnLb = document.getElementById('lightboxLikeBtn');
      if (likeBtnLb) {
        likeBtnLb.addEventListener('click', async () => {
          if (likeBtnLb.dataset.authRequired === '1') {
            window.showToast('Зарегистрируйтесь, чтобы ставить лайки');
            return;
          }
          try {
            const res = await fetch(`/work/${work.id}/like`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
            const data = await res.json();
            if (data.ok) {
              likeBtnLb.classList.toggle('liked', data.liked);
              likeBtnLb.classList.remove('bump'); void likeBtnLb.offsetWidth; likeBtnLb.classList.add('bump');
              document.getElementById('lightboxLikeCount').textContent = data.like_count;
              const pill = document.querySelector(`.card[data-work-id="${work.id}"] .card-like-pill`);
              if (pill) pill.classList.toggle('liked', data.liked);
            }
          } catch (err) { window.showToast('Ошибка сети. Попробуйте ещё раз.'); }
        });
      }

      const form = document.getElementById('lightboxCommentForm');
      if (form) {
        form.addEventListener('submit', async (e) => {
          e.preventDefault();
          const textarea = form.querySelector('textarea');
          const text = textarea.value.trim();
          if (!text) return;
          try {
            const res = await fetch(`/work/${work.id}/comment`, {
              method: 'POST',
              headers: { 'X-Requested-With': 'XMLHttpRequest' },
              body: new URLSearchParams({ text }),
            });
            const data = await res.json();
            if (data.ok) {
              const list = document.getElementById('lightboxCommentList');
              const emptyNote = list.querySelector('.empty-note');
              if (emptyNote) emptyNote.remove();
              list.insertAdjacentHTML('afterbegin', renderComment(data.comment));
              document.getElementById('lightboxCommentCount').textContent = data.comment_count;
              textarea.value = '';
              window.showToast('Комментарий добавлен!');
            } else {
              window.showToast(data.error || 'Не удалось отправить комментарий.');
            }
          } catch (err) { window.showToast('Ошибка сети. Попробуйте ещё раз.'); }
        });
      }

      panel.addEventListener('click', async (e) => {
        const delBtn = e.target.closest('.comment-admin-del');
        if (!delBtn || !isAdmin) return;
        const id = delBtn.dataset.commentId;
        try {
          await fetch(`/admin/comment/${id}/delete`, {
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest', 'Content-Type': 'application/x-www-form-urlencoded' },
            body: new URLSearchParams({ next: window.location.pathname }),
          });
          delBtn.closest('.comment-item').remove();
        } catch (err) { /* тихо игнорируем — комментарий удалится при следующей загрузке */ }
      });
    }

    async function loadWork(id) {
      panel.innerHTML = '<div class="lightbox-loading">Загрузка…</div>';
      try {
        const res = await fetch(`/api/work/${id}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
        const data = await res.json();
        if (data.ok) renderWork(data.work);
      } catch (err) {
        panel.innerHTML = '<div class="lightbox-loading">Не удалось загрузить работу.</div>';
      }
    }

    function openAt(index) {
      collectOrder();
      if (!order.length) return;
      currentIndex = ((index % order.length) + order.length) % order.length;
      overlay.classList.add('show');
      requestAnimationFrame(() => overlay.classList.add('in'));
      document.body.style.overflow = 'hidden';
      loadWork(order[currentIndex]);
    }

    function close() {
      overlay.classList.remove('in');
      document.body.style.overflow = '';
      setTimeout(() => overlay.classList.remove('show'), 300);
    }

    function step(delta) {
      if (currentIndex < 0) return;
      currentIndex = ((currentIndex + delta) % order.length + order.length) % order.length;
      loadWork(order[currentIndex]);
    }

    document.querySelectorAll('.card[data-work-id]').forEach((card) => {
      card.addEventListener('click', (e) => {
        e.preventDefault();
        const id = parseInt(card.dataset.workId, 10);
        collectOrder();
        openAt(order.indexOf(id));
      });
    });

    closeBtn.addEventListener('click', close);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    prevBtn.addEventListener('click', () => step(-1));
    nextBtn.addEventListener('click', () => step(1));
    document.addEventListener('keydown', (e) => {
      if (!overlay.classList.contains('show')) return;
      if (e.key === 'Escape') close();
      if (e.key === 'ArrowLeft') step(-1);
      if (e.key === 'ArrowRight') step(1);
    });
  }

  /* =========================================================
     MUSIC PLAYER — ambient background track with a real
     Web-Audio-reactive equalizer. Browsers block autoplay
     with sound, so playback starts on the first user click.
     ========================================================= */
  const player = document.getElementById('musicPlayer');
  if (player) {
    const audio = document.getElementById('ambientAudio');
    const toggleBtn = document.getElementById('musicToggle');
    const eqBars = player.querySelectorAll('.eq span');
    let audioCtx = null, analyser = null, sourceNode = null, rafId = null;

    function setupAnalyser() {
      if (audioCtx) return;
      try {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        sourceNode = audioCtx.createMediaElementSource(audio);
        analyser = audioCtx.createAnalyser();
        analyser.fftSize = 32;
        sourceNode.connect(analyser);
        analyser.connect(audioCtx.destination);
      } catch (e) { /* Web Audio недоступен — эквалайзер останется декоративным (CSS-анимация) */ }
    }

    function tick() {
      if (!analyser) return;
      const data = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteFrequencyData(data);
      eqBars.forEach((bar, i) => {
        const v = data[i * 2] || 0;
        bar.style.height = Math.max(4, (v / 255) * 20) + 'px';
      });
      rafId = requestAnimationFrame(tick);
    }

    async function play() {
      setupAnalyser();
      if (audioCtx && audioCtx.state === 'suspended') { try { await audioCtx.resume(); } catch (e) {} }
      try {
        await audio.play();
        player.classList.add('playing');
        if (analyser) tick();
      } catch (e) {
        window.showToast('Добавьте файл static/audio/ambient.mp3, чтобы включить музыку');
      }
    }

    function pause() {
      audio.pause();
      player.classList.remove('playing');
      cancelAnimationFrame(rafId);
    }

    toggleBtn.addEventListener('click', () => {
      if (audio.paused) play(); else pause();
    });
  }

})();
