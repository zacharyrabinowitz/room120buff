// Simple JS for Room 120 site:
// - Nav toggle
// - Smooth scroll
// - Footer year
// - Membership + reservation forms -> mailto
// - Gallery overlay viewer

// ===== Nav toggle =====
const navToggle = document.querySelector('.nav-toggle');
const navList = document.querySelector('.nav-list');

if (navToggle && navList) {
  navToggle.addEventListener('click', () => {
    const isOpen = navList.classList.contains('open');
    navList.classList.toggle('open', !isOpen);
    navToggle.setAttribute('aria-expanded', String(!isOpen));
  });
}

// Close nav on link click (mobile)
document.querySelectorAll('.nav-list a[href^="#"]').forEach(link => {
  link.addEventListener('click', () => {
    if (window.innerWidth <= 768 && navList) {
      navList.classList.remove('open');
      navToggle?.setAttribute('aria-expanded', 'false');
    }
  });
});

// ===== Smooth scroll for internal links =====
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    const href = a.getAttribute('href');
    if (!href || href === '#') return;
    const id = href.slice(1);
    const el = document.getElementById(id);
    if (el) {
      e.preventDefault();
      el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ===== Footer year =====
const yearEl = document.getElementById('year');
if (yearEl && !yearEl.textContent) {
  yearEl.textContent = new Date().getFullYear();
}

// ===== Membership form -> mailto =====
const MEMBERSHIP_EMAIL = 'info@room120buffalo.com'; // change if needed
const membershipForm = document.getElementById('membership-form');

if (membershipForm) {
  membershipForm.addEventListener('submit', e => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(membershipForm).entries());

    const subject = encodeURIComponent(`Room 120 Membership Inquiry — ${data.name || ''}`.trim());
    const bodyLines = [
      `Name: ${data.name || ''}`,
      `Email: ${data.email || ''}`,
      `Phone: ${data.phone || 'N/A'}`,
      `Membership Type: ${data.type || ''}`,
      `How they heard about us: ${data.hear || ''}`,
      ``,
      `How they would use Room 120:`,
      `${data.message || ''}`
    ];

    const body = encodeURIComponent(bodyLines.join('\n'));
    window.location.href = `mailto:${MEMBERSHIP_EMAIL}?subject=${subject}&body=${body}`;
    alert('We’re opening your email client so you can send your membership inquiry.');
    membershipForm.reset();
  });
}

// ===== Reservation form -> mailto =====
const RESERVE_EMAIL = 'reservations@room120buffalo.com'; // change if needed
const reserveForm = document.getElementById('reserve-form');

if (reserveForm) {
  reserveForm.addEventListener('submit', e => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(reserveForm).entries());

    const subject = encodeURIComponent(
      `Room 120 Reservation Request — ${data.date || ''} ${data.time || ''} for ${data.party || ''}`
    );

    const bodyLines = [
      `Name: ${data.name || ''}`,
      `Email: ${data.email || ''}`,
      `Member status: ${data.member || ''}`,
      `Date: ${data.date || ''}`,
      `Time: ${data.time || ''}`,
      `Party Size: ${data.party || ''}`,
      ``,
      `Notes:`,
      `${data.notes || ''}`
    ];

    const body = encodeURIComponent(bodyLines.join('\n'));
    window.location.href = `mailto:${RESERVE_EMAIL}?subject=${subject}&body=${body}`;
    alert('We’re opening your email client so you can send your reservation request.');
    reserveForm.reset();
  });
}

// ===== Gallery overlay =====
const galleryItems = document.querySelectorAll('.gallery-item');
const galleryOverlay = document.getElementById('gallery-overlay');
const galleryImage = document.getElementById('gallery-image');
const galleryClose = document.getElementById('gallery-close');

if (galleryOverlay && galleryImage && galleryItems.length) {
  galleryItems.forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      const href = item.getAttribute('href');
      if (!href) return;
      galleryImage.src = href;
      galleryOverlay.classList.add('open');
    });
  });

  galleryClose?.addEventListener('click', () => {
    galleryOverlay.classList.remove('open');
    galleryImage.src = '';
  });

  galleryOverlay.addEventListener('click', e => {
    if (e.target === galleryOverlay) {
      galleryOverlay.classList.remove('open');
      galleryImage.src = '';
    }
  });
}

// ===== Simple parallax effect for hero & band =====
const parallaxEls = document.querySelectorAll('.parallax .hero-bg');

const applyParallax = () => {
  const y = window.scrollY || window.pageYOffset;
  parallaxEls.forEach(el => {
    const section = el.closest('.parallax');
    if (!section) return;
    const rect = section.getBoundingClientRect();
    if (rect.bottom < 0 || rect.top > window.innerHeight) return;
    const offset = (rect.top + y) * -0.25;
    el.style.transform = `translateY(${offset}px)`;
  });
};

applyParallax();
window.addEventListener('scroll', applyParallax, { passive: true });
window.addEventListener('resize', applyParallax);