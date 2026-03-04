/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Helper function to show error in modal
function showErrorInModal(message) {
  const errorContainer = document.getElementById('profileErrorContainer');
  errorContainer.innerHTML = `
    <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
      <h3 class="font-bold mb-2">Error</h3>
      <p class="text-sm">${escapeHtml(message)}</p>
    </div>
  `;
}

