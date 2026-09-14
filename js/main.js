if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  document.documentElement.classList.add('reduce-motion');
}

// Gentle 3D tilt on cards — fine-pointer devices only, respects reduced motion
(function initCardTilt() {
  const canHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (!canHover || document.documentElement.classList.contains('reduce-motion')) return;

  const MAX_TILT = 5; // degrees — subtle, not the fairground-mirror kind
  const cards = document.querySelectorAll(
    '.qual, .service, .step, .timeline-item, .clinic-card, .profile-card, .connect__card:not(.connect__card--placeholder)'
  );

  cards.forEach((el) => {
    let frame = null;

    el.addEventListener('mouseenter', () => { el.style.transition = 'none'; });

    el.addEventListener('mousemove', (e) => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect();
        const px = (e.clientX - rect.left) / rect.width - 0.5;
        const py = (e.clientY - rect.top) / rect.height - 0.5;
        const rotateX = (-py * MAX_TILT).toFixed(2);
        const rotateY = (px * MAX_TILT).toFixed(2);
        el.style.transform = `perspective(700px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-3px)`;
        frame = null;
      });
    });

    el.addEventListener('mouseleave', () => {
      if (frame) { cancelAnimationFrame(frame); frame = null; }
      el.style.transition = '';
      el.style.transform = '';
    });
  });
})();

// Hero portrait — a slightly stronger tilt that follows the cursor across the whole hero
(function initPortraitTilt() {
  const canHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  const portrait = document.querySelector('.hero__portrait');
  const stage = document.querySelector('.hero__visual');
  if (!canHover || !portrait || !stage || document.documentElement.classList.contains('reduce-motion')) return;

  const MAX_TILT = 9;
  let frame = null;

  stage.addEventListener('mousemove', (e) => {
    if (frame) return;
    frame = requestAnimationFrame(() => {
      const rect = stage.getBoundingClientRect();
      const px = (e.clientX - rect.left) / rect.width - 0.5;
      const py = (e.clientY - rect.top) / rect.height - 0.5;
      const rotateX = (-py * MAX_TILT).toFixed(2);
      const rotateY = (px * MAX_TILT).toFixed(2);
      portrait.style.transform = `perspective(1200px) rotateX(${rotateX}deg) rotateY(${rotateY}deg)`;
      frame = null;
    });
  });

  stage.addEventListener('mouseleave', () => {
    if (frame) { cancelAnimationFrame(frame); frame = null; }
    portrait.style.transform = 'perspective(1200px)';
  });
})();

// Theme (Light / Dark)
(function initTheme() {
  const STORAGE_KEY = 'theme';
  const root = document.documentElement;
  const buttons = document.querySelectorAll('.theme-toggle__opt');

  function getStored() {
    try {
      return localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  }

  function apply(theme) {
    root.setAttribute('data-theme', theme === 'dark' ? 'dark' : 'light');
    buttons.forEach((btn) => {
      btn.setAttribute('aria-pressed', String(btn.dataset.themeChoice === theme));
    });
  }

  function setTheme(theme) {
    apply(theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch (e) {
      /* storage unavailable, theme still applies for this view */
    }
  }

  const stored = getStored();
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
  apply(stored || (prefersDark ? 'dark' : 'light'));

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => setTheme(btn.dataset.themeChoice));
  });
})();

// Mobile nav toggle
const navToggle = document.getElementById('navToggle');
const navLinks = document.getElementById('navLinks');

if (navToggle && navLinks) {
  navToggle.addEventListener('click', () => {
    const isOpen = navLinks.classList.toggle('is-open');
    navToggle.setAttribute('aria-expanded', String(isOpen));
  });

  navLinks.querySelectorAll('a').forEach((link) => {
    link.addEventListener('click', () => {
      navLinks.classList.remove('is-open');
      navToggle.setAttribute('aria-expanded', 'false');
    });
  });
}

// Scroll reveal — simple fade/slide, no tilt or count-up gimmicks
const revealEls = document.querySelectorAll('[data-reveal]');

if ('IntersectionObserver' in window && revealEls.length) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: '0px 0px -60px 0px' }
  );
  revealEls.forEach((el) => observer.observe(el));
} else {
  revealEls.forEach((el) => el.classList.add('is-visible'));
}

// Floating "Book Appointment" pill — shown once past the hero, hidden again over the booking form
const floatCta = document.getElementById('floatCta');
const heroEl = document.getElementById('hero');
const bookEl = document.getElementById('book');

if (floatCta && heroEl && bookEl && 'IntersectionObserver' in window) {
  const floatCtaLink = floatCta.querySelector('a');
  let heroVisible = true;
  let bookVisible = false;
  const ctaObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.target === heroEl) heroVisible = entry.isIntersecting;
        if (entry.target === bookEl) bookVisible = entry.isIntersecting;
      });
      const shown = !heroVisible && !bookVisible;
      floatCta.classList.toggle('is-shown', shown);
      floatCta.setAttribute('aria-hidden', String(!shown));
      if (floatCtaLink) floatCtaLink.tabIndex = shown ? 0 : -1;
    },
    { threshold: 0.1 }
  );
  ctaObserver.observe(heroEl);
  ctaObserver.observe(bookEl);
}

// Appointment request form — submits to Formspree (see form's action attribute)
const bookForm = document.getElementById('bookForm');
const bookConfirm = document.getElementById('bookConfirm');
const bookError = document.getElementById('bookError');

if (bookForm && bookConfirm && bookError) {
  bookForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const submitBtn = bookForm.querySelector('button[type="submit"]');
    const originalLabel = submitBtn.textContent;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';
    bookError.hidden = true;

    try {
      const response = await fetch(bookForm.action, {
        method: 'POST',
        body: new FormData(bookForm),
        headers: { Accept: 'application/json' },
      });
      if (!response.ok) throw new Error('Form submission failed');
      bookForm.hidden = true;
      bookConfirm.hidden = false;
      bookConfirm.focus?.();
    } catch (err) {
      submitBtn.disabled = false;
      submitBtn.textContent = originalLabel;
      bookError.hidden = false;
      bookError.focus?.();
    }
  });
}
