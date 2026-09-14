if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  document.documentElement.classList.add('reduce-motion');
}

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
