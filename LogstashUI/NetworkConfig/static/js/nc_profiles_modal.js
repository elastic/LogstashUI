// Network Config - Profiles Modal

const ncAddProfileBtn = document.getElementById('addProfileBtn');
if (ncAddProfileBtn) {
  ncAddProfileBtn.addEventListener('click', function () {
    openProfileModal();
  });
}

function openProfileModal(profileData = null) {
  const modal = document.getElementById('ncProfileFormModal');
  const form = document.getElementById('ncProfileForm');
  const title = document.getElementById('ncProfileModalTitle');

  form.reset();
  document.getElementById('ncProfileErrorContainer').innerHTML = '';

  if (profileData) {
    title.textContent = 'Edit Network Config Profile';
    document.getElementById('ncProfileOriginalName').value = profileData.name;
    document.getElementById('ncProfileName').value = profileData.name || '';
    document.getElementById('ncProfileDescription').value = profileData.description || '';
    document.getElementById('ncProfileVendor').value = profileData.vendor || '';
    document.getElementById('ncProfileType').value = profileData.type || '';
    document.getElementById('ncProfileData').value = JSON.stringify(profileData.profile_data || {}, null, 2);
  } else {
    title.textContent = 'Add Network Config Profile';
    document.getElementById('ncProfileOriginalName').value = '';
    document.getElementById('ncProfileData').value = JSON.stringify({ paths: [] }, null, 2);
  }

  modal.classList.remove('hidden');
  document.body.style.overflow = 'hidden';
}

function closeProfileModal() {
  document.getElementById('ncProfileFormModal').classList.add('hidden');
  document.getElementById('ncProfileForm').reset();
  document.getElementById('ncProfileErrorContainer').innerHTML = '';
  document.body.style.overflow = 'auto';
}

document.getElementById('ncProfileForm').addEventListener('submit', function (e) {
  e.preventDefault();

  const formData = new FormData(this);
  const originalName = document.getElementById('ncProfileOriginalName').value;
  const url = originalName
    ? `/NetworkConfig/UpdateProfile/${encodeURIComponent(originalName)}/`
    : '/NetworkConfig/AddProfile/';

  // Validate JSON before submit
  const profileDataRaw = document.getElementById('ncProfileData').value;
  try {
    JSON.parse(profileDataRaw);
  } catch (err) {
    document.getElementById('ncProfileErrorContainer').innerHTML = `
      <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
        <h3 class="font-bold mb-2">Invalid JSON</h3>
        <p class="text-sm">${err.message}</p>
      </div>`;
    return;
  }

  const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

  fetch(url, {
    method: 'POST',
    headers: { 'X-CSRFToken': csrfToken },
    body: formData,
  })
    .then(response => {
      if (!response.ok) return response.text().then(t => { throw new Error(t || 'Failed to save profile'); });
      return response.json();
    })
    .then(() => {
      showToast(originalName ? 'Profile updated!' : 'Profile created!', 'success');
      closeProfileModal();
      setTimeout(() => window.location.reload(), 500);
    })
    .catch(error => {
      const container = document.getElementById('ncProfileErrorContainer');
      container.innerHTML = `
        <div class="p-4 mb-4 text-red-700 bg-red-100 border border-red-300 rounded-lg">
          <h3 class="font-bold mb-2">Error</h3>
          <p class="text-sm">${error.message}</p>
        </div>`;
      container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
});
