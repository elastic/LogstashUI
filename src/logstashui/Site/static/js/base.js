/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Toast notification function
function showToast(message, type = 'success') {
  const container = document.getElementById('toast-container') || createToastContainer();
  const toast = document.createElement('div');
  const colors = {
    success: 'bg-green-500',
    error: 'bg-red-500',
    info: 'bg-blue-500',
    warning: 'bg-yellow-500'
  };
  toast.className = `${colors[type] || 'bg-gray-800'} text-white px-6 py-3 rounded-lg shadow-lg flex items-center justify-between min-w-[300px]`;
  toast.innerHTML = `
    <span>${escapeHtml(message)}</span>
    <button onclick="this.parentElement.remove()" class="text-white hover:text-gray-200 ml-4">
      <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
      </svg>
    </button>
  `;

  container.appendChild(toast);

  // Auto-remove after 5 seconds
  setTimeout(() => {
    toast.style.opacity = '0';
    setTimeout(() => toast.remove(), 300);
  }, 5000);
}

function createToastContainer() {
  const container = document.createElement('div');
  container.id = 'toast-container';
  container.className = 'fixed top-4 right-4 z-50 flex flex-col gap-2';
  document.body.appendChild(container);
  return container;
}


// Escape HTML to prevent XSS
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// Scroll to top functionality
document.addEventListener('DOMContentLoaded', function() {
  const scrollButton = document.getElementById('scroll-to-top');
  const mainContent = document.querySelector('main');
  const sidebar = document.querySelector('aside');
  const scrollThreshold = 500;

  if (!scrollButton || !mainContent) return;

  // Position button relative to sidebar width
  function positionButton() {
    if (sidebar) {
      const sidebarWidth = sidebar.offsetWidth;
      scrollButton.style.left = `${sidebarWidth + 24}px`; // sidebar width + 1.5rem (24px)
    }
  }

  // Set initial position
  positionButton();

  // Update position on window resize
  window.addEventListener('resize', positionButton);

  // Show/hide button based on scroll position
  mainContent.addEventListener('scroll', function() {
    if (mainContent.scrollTop > scrollThreshold) {
      scrollButton.classList.remove('opacity-0', 'pointer-events-none');
      scrollButton.classList.add('opacity-100', 'pointer-events-auto');
    } else {
      scrollButton.classList.remove('opacity-100', 'pointer-events-auto');
      scrollButton.classList.add('opacity-0', 'pointer-events-none');
    }
  });

  // Scroll to top on button click
  scrollButton.addEventListener('click', function() {
    mainContent.scrollTo({
      top: 0,
      behavior: 'smooth'
    });
  });
});
