// Shared front-end behavior for Habit Tracker

document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss flash messages after a few seconds
  document.querySelectorAll('.flash').forEach((el, i) => {
    setTimeout(() => {
      el.style.transition = 'opacity .4s ease, transform .4s ease';
      el.style.opacity = '0';
      el.style.transform = 'translateY(-6px)';
      setTimeout(() => el.remove(), 400);
    }, 3500 + i * 300);
  });
});
