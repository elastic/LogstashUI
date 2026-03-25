// Network Config - Credentials Modal

const ncAddCredentialBtn = document.getElementById('addCredentialBtn');
if (ncAddCredentialBtn) {
  ncAddCredentialBtn.addEventListener('click', function () {
    openCredentialModal();
  });
}

function openCredentialModal(credentialData = null) {
  const modal = document.getElementById('ncCredentialFormModal');
  const form = document.getElementById('ncCredentialForm');
  const title = document.getElementById('ncCredModalTitle');

  form.reset();
  document.getElementById('ncCredentialErrorContainer').innerHTML = '';

  if (credentialData) {
    title.textContent = 'Edit Network Credential';
    document.getElementById('ncCredentialId').value = credentialData.id;
    document.getElementById('ncCredentialName').value = credentialData.name || '';
    document.getElementById('ncCredentialDescription').value = credentialData.description || '';
    document.getElementById('ncProtocol').value = credentialData.protocol || 'restconf';
    document.getElementById('ncAuthType').value = credentialData.auth_type || 'basic';
    document.getElementById('ncUsername').value = credentialData.username || '';
    document.getElementById('ncApiKeyHeader').value = credentialData.api_key_header || 'X-API-Key';
    document.getElementById('ncVerifySsl').checked = credentialData.verify_ssl !== false;
    // Never populate secret fields when editing
  } else {
    title.textContent = 'Add Network Credential';
    document.getElementById('ncCredentialId').value = '';
    document.getElementById('ncVerifySsl').checked = true;
  }

  updateNCAuthFields();
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeCredentialModal() {
  document.getElementById('ncCredentialFormModal').classList.add('hidden');
  document.getElementById('ncCredentialForm').reset();
  document.getElementById('ncCredentialErrorContainer').innerHTML = '';
  document.body.style.overflow = 'auto';

  // If called from device modal, refresh credential dropdown
  const deviceModal = document.getElementById('ncDeviceFormModal');
  if (deviceModal && !deviceModal.classList.contains('hidden')) {
    loadNCCredentialOptions();
  }
}

function updateNCAuthFields() {
  const authType = document.getElementById('ncAuthType').value;
  document.getElementById('ncBasicFields').classList.toggle('hidden', authType !== 'basic');
  document.getElementById('ncTokenFields').classList.toggle('hidden', authType !== 'token');
  document.getElementById('ncApiKeyFields').classList.toggle('hidden', authType !== 'api_key');
}

document.getElementById('ncCredentialForm').addEventListener('submit', function (e) {
  e.preventDefault();

  const formData = new FormData(this);
  const credentialId = document.getElementById('ncCredentialId').value;
  const url = credentialId
    ? `/NetworkConfig/UpdateCredential/${credentialId}/`
    : '/NetworkConfig/AddCredential/';

  // Encode verify_ssl as string for the backend
  formData.set('verify_ssl', document.getElementById('ncVerifySsl').checked ? 'true' : 'false');

  // Consolidate token field from whichever auth type is active
  const authType = document.getElementById('ncAuthType').value;
  if (authType === 'api_key') {
    const apiKeyVal = document.getElementById('ncApiKeyToken').value;
    formData.set('token', apiKeyVal);
  }

  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  fetch(url, {
    method: 'POST',
    headers: { 'X-CSRFToken': csrfToken },
    body: formData,
  })
    .then(response => {
      if (!response.ok) return response.text().then(t => { throw new Error(t || 'Failed to save credential'); });
      return response.json();
    })
    .then(() => {
      showToast(credentialId ? 'Credential updated!' : 'Credential created!', 'success');
      closeCredentialModal();
      setTimeout(() => window.location.reload(), 500);
    })
    .catch(error => {
      const container = document.getElementById('ncCredentialErrorContainer');
      container.innerHTML = `
        <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
          <h3 class="font-bold mb-2">Error</h3>
          <p class="text-sm">${error.message}</p>
        </div>`;
      container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
});
