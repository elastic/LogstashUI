/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Discovered Devices Modal Functions

// Whether to include DNS-resolved devices that did not respond via SNMP.
// Toggled by the checkbox in discovered_devices_content.html.
let _showNonSnmpDevices = false;

function openDiscoveredDevicesModal() {
    const modal = document.getElementById('discoveredDevicesModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    
    // Load discovered devices
    loadDiscoveredDevices();
}

function closeDiscoveredDevicesModal() {
    const modal = document.getElementById('discoveredDevicesModal');
    if (!modal) return;
    modal.classList.add('hidden');
    document.body.style.overflow = 'auto';
}

/** Toggle DNS-only device visibility and reload the table. */
function toggleNonSnmpDevices() {
    const checkbox = document.getElementById('showNonSnmpToggle');
    _showNonSnmpDevices = checkbox ? checkbox.checked : !_showNonSnmpDevices;
    loadDiscoveredDevices();
}

function loadDiscoveredDevices() {
    // Show loading state
    document.getElementById('discoveredDevicesLoading').classList.remove('hidden');
    document.getElementById('discoveredDevicesError').classList.add('hidden');
    document.getElementById('discoveredDevicesEmpty').classList.add('hidden');
    document.getElementById('discoveredDevicesTable').classList.add('hidden');
    document.getElementById('discoveredDevicesControls').classList.add('hidden');
    
    // Fetch discovered devices from API
    const url = `/SNMP/DiscoveredDevices/?show_non_snmp=${_showNonSnmpDevices}`;
    fetch(url, {
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
            // Controls (toggle + banner) are always shown once we have a response
            // so the user can enable the DNS toggle even when 0 SNMP devices responded.
            document.getElementById('discoveredDevicesControls').classList.remove('hidden');

            // When the DNS toggle is on, filter locally: only keep rows where
            // host_hostname resolved to a real name (not a bare IP address).
            // The backend still returns everything; we just don't render noise.
            let devicesToShow = data.devices || [];
            if (_showNonSnmpDevices) {
                devicesToShow = devicesToShow.filter(
                    d => d.host_hostname && !_isIpAddress(d.host_hostname)
                );
            }

            const hasDiscovered = devicesToShow.length > 0;
            if (hasDiscovered) {
                // Show table and populate it
                document.getElementById('discoveredDevicesTable').classList.remove('hidden');
                populateDiscoveredDevicesTable(devicesToShow);
                document.getElementById('discoveredDevicesCount').textContent = devicesToShow.length;
            } else {
                // Show empty state (controls are still visible above it)
                document.getElementById('discoveredDevicesEmpty').classList.remove('hidden');
                document.getElementById('discoveredDevicesCount').textContent = '0';
            }
            
            // Show any errors from connections
            if (data.errors && data.errors.length > 0) {
                console.warn('Some connections had errors:', data.errors);
            }

            // Notify smart tab selector (one-shot hook set by Onboarding.html)
            if (typeof window._onDiscoveredDevicesLoaded === 'function') {
                window._onDiscoveredDevicesLoaded(hasDiscovered);
            }
        } else {
            // Show error state
            showDiscoveredDevicesError(data.error || 'Failed to load discovered devices');
            if (typeof window._onDiscoveredDevicesLoaded === 'function') {
                window._onDiscoveredDevicesLoaded(false);
            }
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

// Returns true when value is an IPv4 or IPv6 address rather than a hostname.
// Used to detect when DNS resolution failed and host.hostname still holds an IP.
function _isIpAddress(value) {
    if (!value) return false;
    if (/^\d{1,3}(\.\d{1,3}){3}$/.test(value)) return true;  // IPv4
    if (/^[0-9a-fA-F:]{2,39}$/.test(value) && value.includes(':')) return true;  // IPv6
    return false;
}

function populateDiscoveredDevicesTable(devices) {
    const tbody = document.getElementById('discoveredDevicesTableBody');
    tbody.innerHTML = '';
    
    devices.forEach((device, index) => {
        const row = document.createElement('tr');
        row.className = 'hover:bg-gray-700/50';
        
        // Store device data in a global array for access by the button
        if (!window.discoveredDevicesData) {
            window.discoveredDevicesData = [];
        }
        window.discoveredDevicesData[index] = device;

        // Resolve what to show in each column.
        // host_hostname is DNS-resolved; if DNS failed it will still be an IP.
        const resolvedHostname = (device.host_hostname && !_isIpAddress(device.host_hostname))
            ? device.host_hostname
            : null;
        const resolvedIp = device.host_ip
            || (_isIpAddress(device.host_hostname) ? device.host_hostname : null)
            || null;

        const hostnameCell = resolvedHostname
            ? `<span class="font-mono text-white">${escapeHtml(resolvedHostname)}</span>`
            : '<span class="text-gray-500 italic">—</span>';
        const ipCell = resolvedIp
            ? `<span class="font-mono">${escapeHtml(resolvedIp)}</span>`
            : '<span class="text-gray-500 italic">—</span>';
        
        // Format suggested template display
        let suggestedTemplateHtml = '<span class="text-gray-500 text-xs">None</span>';
        if (device.suggested_template_name) {
            suggestedTemplateHtml = `
                <span class="inline-flex items-center px-2 py-1 rounded-md text-xs font-medium bg-blue-500/20 text-blue-300 border border-blue-500/40">
                    <svg class="w-3 h-3 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    ${escapeHtml(device.suggested_template_name)}
                </span>
            `;
        }
        
        // Prepare OS description for tooltip (sysDescr from SNMP)
        const sysDescr = device.sys_descr || 'No description available';
        const hostName = device.host_name || 'N/A';

        // Non-SNMP devices: SNMP timed out. Dim the row slightly.
        const isNonSnmp = device.snmp_responded === false;
        if (isNonSnmp) {
            row.className = 'hover:bg-gray-700/50 opacity-60';
        }

        // Show the "DNS only" pill next to the hostname, but only when DNS
        // actually resolved a real name (resolvedHostname is non-null).
        const dnsOnlyBadge = (isNonSnmp && resolvedHostname)
            ? `<span class="ml-2 inline-flex items-center px-1.5 py-0.5 rounded text-xs font-medium bg-amber-500/20 text-amber-300 border border-amber-500/40" title="Hostname resolved via DNS; device did not respond to SNMP">DNS only</span>`
            : '';

        row.innerHTML = `
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                <span class="device-name-tooltip cursor-help border-b border-dotted border-gray-500 hover:border-blue-400 hover:text-blue-300 transition-colors" data-tooltip="${escapeHtml(sysDescr)}">
                    ${escapeHtml(hostName)}
                </span>
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                ${hostnameCell}${dnsOnlyBadge}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                ${ipCell}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
                ${escapeHtml(device.network_name || 'N/A')}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-400">
                ${escapeHtml(device.connection_name || 'N/A')}
            </td>
            <td class="px-6 py-4 whitespace-nowrap text-sm">
                ${suggestedTemplateHtml}
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

    // host_ip always goes to the IP field.
    // host_hostname goes to the Hostname field only when it is a real hostname
    // (DNS succeeded). If DNS failed, host_hostname is the same IP as host_ip,
    // so we discard it rather than populating the wrong field.
    const ipAddress = device.host_ip || (_isIpAddress(device.host_hostname) ? device.host_hostname : '') || '';
    const hostname  = (device.host_hostname && !_isIpAddress(device.host_hostname)) ? device.host_hostname : '';

    // Open the device modal with pre-filled data
    if (typeof openDeviceModal === 'function') {
        openDeviceModal({
            name: device.host_name,
            hostname: hostname,
            ip_address: ipAddress,
            credential: device.credential_id,
            network: device.network_id,
            device_template: device.suggested_template_id
        });
    } else {
        console.error('openDeviceModal function not found');
    }
}


// Instant tooltip handler for device names
let tooltipElement = null;

document.addEventListener('mouseover', function(e) {
    const target = e.target.closest('.device-name-tooltip');
    if (target && target.dataset.tooltip) {
        // Create tooltip if it doesn't exist
        if (!tooltipElement) {
            tooltipElement = document.createElement('div');
            tooltipElement.className = 'fixed px-3 py-2 bg-gray-900 text-white text-xs rounded-lg shadow-lg border border-gray-700 pointer-events-none';
            tooltipElement.style.zIndex = '10000';
            tooltipElement.style.maxWidth = '400px';
            tooltipElement.style.whiteSpace = 'pre-wrap';
            document.body.appendChild(tooltipElement);
        }
        
        // Set content and show
        tooltipElement.textContent = target.dataset.tooltip;
        tooltipElement.style.display = 'block';
        
        // Position below the element
        const rect = target.getBoundingClientRect();
        tooltipElement.style.left = rect.left + (rect.width / 2) - (tooltipElement.offsetWidth / 2) + 'px';
        tooltipElement.style.top = rect.bottom + 8 + 'px';
    }
});

document.addEventListener('mouseout', function(e) {
    const target = e.target.closest('.device-name-tooltip');
    if (target && tooltipElement) {
        tooltipElement.style.display = 'none';
    }
});

// Attach event listener to discovered devices button
document.addEventListener('DOMContentLoaded', function() {
    const discoveredDevicesBtn = document.getElementById('discoveredDevicesBtn');
    if (discoveredDevicesBtn) {
        discoveredDevicesBtn.addEventListener('click', openDiscoveredDevicesModal);
    }
});
