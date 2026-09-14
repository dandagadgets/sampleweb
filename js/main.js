if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
  document.documentElement.classList.add('reduce-motion');
}

// Subtle 3D hover tilt on card tiles (fine-pointer devices only, respects reduced motion)
(function initTilt() {
  const canHover = window.matchMedia('(hover: hover) and (pointer: fine)').matches;
  if (!canHover || document.documentElement.classList.contains('reduce-motion')) return;

  const MAX_TILT = 7; // degrees
  const els = document.querySelectorAll(
    '.qual, .service, .step, .timeline-item, .clinic-card, .facts-card, .doctor-card, .connect__card:not(.connect__card--placeholder), .hstat, .chip, .badge'
  );

  els.forEach((el) => {
    let frame = null;

    el.addEventListener('mouseenter', () => {
      el.style.transition = 'none';
    });

    el.addEventListener('mousemove', (e) => {
      if (frame) return;
      frame = requestAnimationFrame(() => {
        const rect = el.getBoundingClientRect();
        const px = (e.clientX - rect.left) / rect.width - 0.5;
        const py = (e.clientY - rect.top) / rect.height - 0.5;
        const rotateX = (-py * MAX_TILT).toFixed(2);
        const rotateY = (px * MAX_TILT).toFixed(2);
        el.style.transform = `perspective(700px) rotateX(${rotateX}deg) rotateY(${rotateY}deg) translateY(-4px)`;
        frame = null;
      });
    });

    el.addEventListener('mouseleave', () => {
      if (frame) {
        cancelAnimationFrame(frame);
        frame = null;
      }
      el.style.transition = '';
      el.style.transform = '';
    });
  });
})();

// Scroll-linked parallax depth: background dots and decorative blobs
// drift at different speeds than the page content, so scrolling itself
// reads as moving through layers rather than a flat 2D page.
(function initParallax() {
  if (document.documentElement.classList.contains('reduce-motion')) return;

  const blobs = document.querySelectorAll('.blob');
  let ticking = false;

  function update() {
    const y = window.scrollY;
    document.body.style.setProperty('--dots-parallax', (y * 0.12).toFixed(1) + 'px');
    blobs.forEach((el, i) => {
      const speed = 0.06 + (i % 3) * 0.025;
      el.style.transform = `translateY(${(y * speed).toFixed(1)}px)`;
    });
    ticking = false;
  }

  window.addEventListener(
    'scroll',
    () => {
      if (!ticking) {
        requestAnimationFrame(update);
        ticking = true;
      }
    },
    { passive: true }
  );

  update();
})();

// Theme (White / Black)
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
    if (theme === 'dark') {
      root.setAttribute('data-theme', 'dark');
    } else {
      root.setAttribute('data-theme', 'light');
    }
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

// Animated count-up for stat numbers
function animateCount(el) {
  const target = parseFloat(el.dataset.count);
  if (Number.isNaN(target)) return;
  const decimals = el.dataset.decimals ? parseInt(el.dataset.decimals, 10) : 0;
  const suffix = el.dataset.suffix || '';
  const prefix = el.dataset.prefix || '';
  const duration = 1200;

  if (document.documentElement.classList.contains('reduce-motion')) {
    const value = target.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    el.textContent = prefix + value + suffix;
    return;
  }

  let startTime = null;
  function step(ts) {
    if (!startTime) startTime = ts;
    const progress = Math.min((ts - startTime) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    const value = (target * eased).toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
    el.textContent = prefix + value + suffix;
    if (progress < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// Scroll reveal (also triggers count-up for any [data-count] inside)
const revealEls = document.querySelectorAll('[data-reveal]');

if ('IntersectionObserver' in window && revealEls.length) {
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('is-visible');
          entry.target.querySelectorAll('[data-count]').forEach(animateCount);
          observer.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.15, rootMargin: '0px 0px -60px 0px' }
  );
  revealEls.forEach((el) => observer.observe(el));
} else {
  revealEls.forEach((el) => {
    el.classList.add('is-visible');
    el.querySelectorAll('[data-count]').forEach(animateCount);
  });
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
