/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Close commit modal
function closeCommitModal() {
  const modal = document.getElementById('commitModal');
  modal.classList.add('hidden');
  document.body.style.overflow = 'auto';
}



// Get CSRF token from cookies
function getCsrfToken() {
  const name = 'csrftoken';
  let cookieValue = null;
  if (document.cookie && document.cookie !== '') {
    const cookies = document.cookie.split(';');
    for (let i = 0; i < cookies.length; i++) {
      const cookie = cookies[i].trim();
      if (cookie.substring(0, name.length + 1) === (name + '=')) {
        cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
        break;
      }
    }
  }
  return cookieValue;
}

// Attach event listener to commit button
document.addEventListener('DOMContentLoaded', function () {
  const commitBtn = document.getElementById('commitBtn');
  if (commitBtn) {
    commitBtn.addEventListener('click', prepareSnmpDiffModal);
  }
});
