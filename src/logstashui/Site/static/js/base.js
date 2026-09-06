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
  if (text === null || text === undefined) return '';
  const div = document.createElement('div');
  div.textContent = String(text);
  return div.innerHTML;
}

// Convert a slug-style identifier (e.g. 'dell_x1026', 'generic_interfaces.json')
// into a human-friendly display label (e.g. 'Dell X1026', 'Generic Interfaces').
// Mirrors Common/formatters.py:format_display_name - used as a client-side
// fallback when an API response only provides the raw name/slug.
function formatDisplayName(name) {
  if (!name) return '';
  let label = String(name);
  if (label.endsWith('.json')) {
    label = label.slice(0, -5);
  }
  return label
    .replace(/[_-]+/g, ' ')
    .split(' ')
    .filter(Boolean)
    .map(word => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ');
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

/**
 * Wraps a modal close function with a styled "Are you sure?" confirmation dialog.
 * Use on backdrop onclick handlers for form-heavy modals to prevent accidental data loss.
 * X and Cancel buttons should still call the close function directly (intentional close).
 *
 * Opt a modal in by:
 *   1. Adding the data-confirm-close attribute to the root modal element.
 *   2. Changing the backdrop onclick from closeXxxModal() to safeClose(closeXxxModal).
 *
 * @param {Function} closeFn - The close function to invoke if the user confirms.
 */
window.safeClose = async function(closeFn) {
  const confirmed = await ConfirmationModal.show(
    'Are you sure you want to close? Any unsaved changes will be lost.',
    'Unsaved Changes',
    'Close Anyway'
  );
  if (confirmed) closeFn();
};

// Global ESC key handler to close any open modal
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape' || e.key === 'Esc') {
    // Find any modal that's currently visible (not hidden)
    // Only select elements that end with Modal or Flyout (not child elements)
    const allModals = document.querySelectorAll('[id$="Modal"], [id$="Flyout"]');
    
    const visibleModals = Array.from(allModals).filter(modal => {
      return !modal.classList.contains('hidden');
    });
    
    if (visibleModals.length > 0) {
      // Close the topmost modal (last in the array if multiple open)
      const modalToClose = visibleModals[visibleModals.length - 1];
      const modalId = modalToClose.id;
      const needsConfirmation = modalToClose.hasAttribute('data-confirm-close');
      
      // Build possible close function names
      // Examples: credentialFormModal -> closeCredentialFormModal, closeCredentialModal
      const baseName = modalId.replace(/Modal$|Flyout$/, '');
      const possibleCloseFunctions = [
        'close' + modalId.charAt(0).toUpperCase() + modalId.slice(1),
        'close' + baseName.charAt(0).toUpperCase() + baseName.slice(1) + 'Modal',
        'close' + baseName.charAt(0).toUpperCase() + baseName.slice(1) + 'Flyout',
        'close' + baseName.charAt(0).toUpperCase() + baseName.slice(1)
      ];
      
      let functionCalled = false;
      for (const funcName of possibleCloseFunctions) {
        if (typeof window[funcName] === 'function') {
          if (needsConfirmation) {
            // Stop other ESC listeners (e.g. popup.html's ConfirmationModal.cancel handler)
            // from firing on the same keypress, otherwise they'd immediately dismiss
            // the confirmation dialog we're about to show.
            e.stopImmediatePropagation();
            safeClose(window[funcName]);
          } else {
            window[funcName]();
          }
          functionCalled = true;
          break;
        }
      }
      
      // If no close function found, just hide the modal (with confirmation if opted-in)
      if (!functionCalled) {
        if (needsConfirmation) {
          e.stopImmediatePropagation();
          safeClose(() => modalToClose.classList.add('hidden'));
        } else {
          modalToClose.classList.add('hidden');
        }
      }
    }
  }
});
