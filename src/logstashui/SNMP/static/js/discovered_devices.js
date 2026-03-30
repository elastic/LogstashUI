/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Discovered Devices Modal Functions

function openDiscoveredDevicesModal() {
    const modal = document.getElementById('discoveredDevicesModal');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    
    // Load discovered devices
    loadDiscoveredDevices();
}

function closeDiscoveredDevicesModal() {
    const modal = document.getElementById('discoveredDevicesModal');
    modal.classList.add('hidden');
    document.body.style.overflow = 'auto';
}

function loadDiscoveredDevices() {
    // Show loading state
    document.getElementById('discoveredDevicesLoading').classList.remove('hidden');
    document.getElementById('discoveredDevicesError').classList.add('hidden');
    document.getElementById('discoveredDevicesEmpty').classList.add('hidden');
    document.getElementById('discoveredDevicesTable').classList.add('hidden');
    
    // Fetch discovered devices from API
    fetch('/SNMP/DiscoveredDevices/', {
        method: 'GET',
        headers: {
            'Content-Type': 'application/json',
        }
    })
    .then(response => response.json())
    .then(data => {
        // Hide loading state
        document.getElementById('discoveredDevicesLoading').classList.add('hidden');
        
        if (data.success) {
            if (data.devices && data.devices.length > 0) {
                // Show table and populate it
                document.getElementById('discoveredDevicesTable').classList.remove('hidden');
                populateDiscoveredDevicesTable(data.devices);
                document.getElementById('discoveredDevicesCount').textContent = data.total;
            } else {
                // Show empty state
                document.getElementById('discoveredDevicesEmpty').classList.remove('hidden');
                document.getElementById('discoveredDevicesCount').textContent = '0';
            }
            
            // Show any errors from connections
            if (data.errors && data.errors.length > 0) {
                console.warn('Some connections had errors:', data.errors);
            }
        } else {
            // Show error state
            showDiscoveredDevicesError(data.error || 'Failed to load discovered devices');
        }
    })
    .catch(error => {
        console.error('Error loading discovered devices:', error);
        document.getElementById('discoveredDevicesLoading').classList.add('hidden');
        showDiscoveredDevicesError('Network error: ' + error.message);
    });
}

function showDiscoveredDevicesError(message) {
    document.getElementById('discoveredDevicesError').classList.remove('hidden');
    document.getElementById('discoveredDevicesErrorMessage').textContent = message;
    document.getElementById('discoveredDevicesCount').textContent = '0';
}

function populateDiscoveredDevicesTable(devices) {
    const tbody = document.getElementById('discoveredDevicesTableBody');
    tbody.innerHTML = '';
    
    devices.forEach((device, index) => {
        const row = document.createElement('tr');
        row.className = 'hover:bg-gray-700/50';
        
        // Use hostname if available, otherwise use IP
        const ipOrHostname = device.host_hostname || device.host_ip || 'N/A';
        
        // Store device data in a global array for access by the button
        if (!window.discoveredDevicesData) {
            window.discoveredDevicesData = [];
        }
        window.discoveredDevicesData[index] = device;
        
        row.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                ${escapeHtml(device.host_name || 'N/A')}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                ${escapeHtml(ipOrHostname)}
            </td>
            <td class="px-6 py-4 text-sm text-gray-300">
                ${escapeHtml(device.host_os_full || 'N/A')}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                ${escapeHtml(device.network_name || 'N/A')}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                ${escapeHtml(device.connection_name || 'N/A')}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-right text-sm">
                <button 
                    onclick="addDiscoveredDevice(${index})"
                    class="btn btn-sm btn-primary">
                    + Add
                </button>
            </td>
        `;
        
        tbody.appendChild(row);
    });
}

function addDiscoveredDevice(deviceIndex) {
    // Get the device data from the global array
    const device = window.discoveredDevicesData[deviceIndex];
    if (!device) {
        console.error('Device data not found for index:', deviceIndex);
        return;
    }
    
    // Close the discovered devices modal
    closeDiscoveredDevicesModal();
    
    // Use hostname if available, otherwise use IP
    const ipOrHostname = device.host_hostname || device.host_ip || '';
    
    // Open the device modal with pre-filled data
    // The openDeviceModal function is defined in snmp_devices_modal.js
    if (typeof openDeviceModal === 'function') {
        openDeviceModal({
            name: device.host_name,
            ip_address: ipOrHostname,
            credential: device.credential_id,
            network: device.network_id,
            profiles: ['system']  // Pre-select system profile
        });
    } else {
        console.error('openDeviceModal function not found');
    }
}


// Attach event listener to discovered devices button
document.addEventListener('DOMContentLoaded', function() {
    const discoveredDevicesBtn = document.getElementById('discoveredDevicesBtn');
    if (discoveredDevicesBtn) {
        discoveredDevicesBtn.addEventListener('click', openDiscoveredDevicesModal);
    }
});
