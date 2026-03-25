// Network Config - Devices Modal

const ncAddDeviceBtn = document.getElementById('addDeviceBtn');
if (ncAddDeviceBtn) {
  ncAddDeviceBtn.addEventListener('click', openDeviceModal);
}

const ncAddDeviceBtnEmpty = document.getElementById('addDeviceBtnEmpty');
if (ncAddDeviceBtnEmpty) {
  ncAddDeviceBtnEmpty.addEventListener('click', openDeviceModal);
}

function openDeviceModal(deviceData = null) {
  const modal = document.getElementById('ncDeviceFormModal');
  const form = document.getElementById('ncDeviceForm');
  const title = document.getElementById('ncDeviceModalTitle');

  form.reset();
  document.getElementById('ncDeviceErrorContainer').innerHTML = '';

  // Load credential and profile options
  loadNCCredentialOptions();
  loadNCProfileOptions();

  if (deviceData) {
    title.textContent = 'Edit Network Device';
    document.getElementById('ncDeviceId').value = deviceData.id;
    document.getElementById('ncDeviceName').value = deviceData.name || '';
    document.getElementById('ncDeviceDescription').value = deviceData.description || '';
    document.getElementById('ncVendor').value = deviceData.vendor || 'generic';
    document.getElementById('ncHostname').value = deviceData.hostname || '';
    document.getElementById('ncRestPort').value = deviceData.rest_port || 443;
    document.getElementById('ncNetconfPort').value = deviceData.netconf_port || 830;
    document.getElementById('ncUseRestconf').checked = deviceData.use_restconf !== false;
    document.getElementById('ncUseNetconf').checked = deviceData.use_netconf === true;

    // Credential / profile selects populated after fetch
    window._ncPendingCredentialId = deviceData.credential_id;
    window._ncPendingProfileId = deviceData.profile_id;
  } else {
    title.textContent = 'Add Network Device';
    document.getElementById('ncDeviceId').value = '';
    document.getElementById('ncUseRestconf').checked = true;
    document.getElementById('ncUseNetconf').checked = false;
    document.getElementById('ncRestPort').value = 443;
    document.getElementById('ncNetconfPort').value = 830;
    window._ncPendingCredentialId = null;
    window._ncPendingProfileId = null;
  }

  updatePortFields();
  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeDeviceModal() {
  document.getElementById('ncDeviceFormModal').classList.add('hidden');
  document.getElementById('ncDeviceForm').reset();
  document.getElementById('ncDeviceErrorContainer').innerHTML = '';
  document.body.style.overflow = 'auto';
}

function updatePortFields() {
  const useRestconf = document.getElementById('ncUseRestconf').checked;
  const useNetconf = document.getElementById('ncUseNetconf').checked;
  document.getElementById('ncRestPortField').classList.toggle('hidden', !useRestconf);
  document.getElementById('ncNetconfPortField').classList.toggle('hidden', !useNetconf);
}

function loadNCCredentialOptions() {
  const select = document.getElementById('ncDeviceCredential');
  fetch('/NetworkConfig/GetCredentials/')
    .then(r => r.json())
    .then(data => {
      select.innerHTML = '<option value="">None</option>';
      data.forEach(cred => {
        const opt = document.createElement('option');
        opt.value = cred.id;
        opt.textContent = `${cred.name} (${cred.protocol})`;
        select.appendChild(opt);
      });
      if (window._ncPendingCredentialId) {
        select.value = window._ncPendingCredentialId;
      }
    })
    .catch(() => {});
}

function loadNCProfileOptions() {
  const select = document.getElementById('ncDeviceProfile');
  fetch('/NetworkConfig/GetProfiles/')
    .then(r => r.json())
    .then(data => {
      select.innerHTML = '<option value="">None</option>';
      data.forEach(profile => {
        const opt = document.createElement('option');
        opt.value = profile.id;
        opt.textContent = profile.name;
        select.appendChild(opt);
      });
      if (window._ncPendingProfileId) {
        select.value = window._ncPendingProfileId;
      }
    })
    .catch(() => {});
}

document.getElementById('ncDeviceForm').addEventListener('submit', function (e) {
  e.preventDefault();

  const formData = new FormData(this);
  const deviceId = document.getElementById('ncDeviceId').value;
  const url = deviceId
    ? `/NetworkConfig/UpdateDevice/${deviceId}/`
    : '/NetworkConfig/AddDevice/';

  // Encode checkboxes explicitly (unchecked boxes are not in FormData)
  formData.set('use_restconf', document.getElementById('ncUseRestconf').checked ? 'true' : 'false');
  formData.set('use_netconf', document.getElementById('ncUseNetconf').checked ? 'true' : 'false');

  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  fetch(url, {
    method: 'POST',
    headers: { 'X-CSRFToken': csrfToken },
    body: formData,
  })
    .then(response => {
      if (!response.ok) return response.text().then(t => { throw new Error(t || 'Failed to save device'); });
      return response.json();
    })
    .then(() => {
      showToast(deviceId ? 'Device updated!' : 'Device created!', 'success');
      closeDeviceModal();
      loadDevices();
    })
    .catch(error => {
      const container = document.getElementById('ncDeviceErrorContainer');
      container.innerHTML = `
        <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
          <h3 class="font-bold mb-2">Error</h3>
          <p class="text-sm">${error.message}</p>
        </div>`;
      container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
});
