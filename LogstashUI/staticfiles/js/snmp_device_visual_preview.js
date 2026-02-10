// Device Visual Preview - Handle expand/collapse and data fetching

// Toggle device preview row
function toggleDevicePreview(deviceId) {
  const previewRow = document.getElementById(`device-preview-${deviceId}`);
  const chevron = document.getElementById(`chevron-${deviceId}`);
  const contentDiv = document.getElementById(`device-preview-content-${deviceId}`);
  
  if (previewRow.classList.contains('hidden')) {
    // Expand the row
    previewRow.classList.remove('hidden');
    chevron.classList.add('rotate-180');
    
    // Check if content is already loaded
    if (contentDiv.innerHTML === '') {
      // Show loading indicator
      const indicator = previewRow.querySelector('.htmx-indicator');
      indicator.classList.remove('hidden');
      
      // Fetch device visualization data
      fetch(`/API/SNMP/GetDeviceVisualization/${deviceId}/`)
        .then(response => response.json())
        .then(data => {
          indicator.classList.add('hidden');
          
          if (data.success) {
            renderDevicePreview(deviceId, data.device, data.visualizations);
          } else {
            contentDiv.innerHTML = `
              <div class="text-center text-red-400 py-4">
                <p>Error loading device data: ${data.error}</p>
              </div>
            `;
          }
        })
        .catch(error => {
          indicator.classList.add('hidden');
          contentDiv.innerHTML = `
            <div class="text-center text-red-400 py-4">
              <p>Error loading device data: ${error.message}</p>
            </div>
          `;
        });
    }
  } else {
    // Collapse the row
    previewRow.classList.add('hidden');
    chevron.classList.remove('rotate-180');
  }
}

// Render device preview content
function renderDevicePreview(deviceId, device, visualizations) {
  const contentDiv = document.getElementById(`device-preview-content-${deviceId}`);
  const template = document.getElementById('device-preview-template');
  
  if (!template) {
    console.error('Device preview template not found');
    return;
  }
  
  // Clone the template
  const clone = template.content.cloneNode(true);
  
  // Populate device info
  clone.querySelector('.device-ip').textContent = device.ip_address;
  clone.querySelector('.device-port').textContent = device.port;
  clone.querySelector('.device-timeout').textContent = `${device.timeout}ms`;
  clone.querySelector('.device-retries').textContent = device.retries;
  
  // Populate network info
  if (device.network) {
    clone.querySelector('.network-name').textContent = device.network.name;
    clone.querySelector('.network-range').textContent = device.network.network_range;
  } else {
    clone.querySelector('.network-name').textContent = 'None';
    clone.querySelector('.network-range').textContent = '-';
  }
  
  // Populate credential info
  if (device.credential) {
    clone.querySelector('.credential-name').textContent = device.credential.name;
    clone.querySelector('.credential-version').textContent = `SNMPv${device.credential.version}`;
  } else {
    clone.querySelector('.credential-name').textContent = 'None';
    clone.querySelector('.credential-version').textContent = '-';
  }
  
  // Populate profiles
  const profilesList = clone.querySelector('.device-profiles-list');
  if (device.profiles && device.profiles.length > 0) {
    device.profiles.forEach(profile => {
      const profileBadge = document.createElement('div');
      profileBadge.className = 'bg-blue-600/20 text-blue-300 px-3 py-1 rounded-md text-sm flex items-center gap-2';
      profileBadge.innerHTML = `
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <div>
          <div class="font-medium">${escapeHtml(profile.name)}</div>
          ${profile.type || profile.vendor ? `<div class="text-xs text-gray-400">${escapeHtml(profile.type || '')} ${profile.vendor ? '• ' + escapeHtml(profile.vendor) : ''}</div>` : ''}
        </div>
      `;
      profilesList.appendChild(profileBadge);
    });
  } else {
    profilesList.innerHTML = '<span class="text-gray-400 italic">No profiles assigned</span>';
  }
  
  // Populate metrics if available
  if (visualizations && visualizations.metrics) {
    const metrics = visualizations.metrics;
    
    // Uptime - convert from hundredths of seconds to human-readable format
    if (metrics.Uptime !== undefined) {
      clone.querySelector('.metric-uptime').textContent = formatUptime(metrics.Uptime);
    }
  } else {
    // Hide metrics section if no visualization data available
    const metricsSection = clone.querySelector('.device-metrics-section');
    if (metricsSection) {
      metricsSection.style.display = 'none';
    }
  }
  
  // Clear and append the populated template
  contentDiv.innerHTML = '';
  contentDiv.appendChild(clone);
  
  // Render charts after DOM insertion (charts need to be in DOM to render)
  if (visualizations && visualizations.metrics) {
    const metrics = visualizations.metrics;
    
    // Render CPU chart
    if (metrics.CPU && metrics.Time && metrics.CPU.length > 0) {
      renderMetricChart(
        contentDiv.querySelector('.metric-cpu-chart'),
        metrics.Time,
        metrics.CPU,
        'CPU Usage (%)',
        'rgba(59, 130, 246, 1)', // Blue
        'rgba(59, 130, 246, 0.1)'
      );
    }
    
    // Render Memory chart
    if (metrics.Memory && metrics.Time && metrics.Memory.length > 0) {
      renderMetricChart(
        contentDiv.querySelector('.metric-memory-chart'),
        metrics.Time,
        metrics.Memory,
        'Memory Usage (%)',
        'rgba(16, 185, 129, 1)', // Green
        'rgba(16, 185, 129, 0.1)'
      );
    }
  }
}

// Render a metric line chart
function renderMetricChart(canvas, timeData, metricData, label, borderColor, backgroundColor) {
  if (!canvas || !timeData || !metricData) return;
  
  // Parse ISO timestamp strings to Date objects and create paired data
  const pairedData = timeData.map((timestamp, index) => ({
    time: new Date(timestamp),
    value: metricData[index] * 100  // Convert to percentage
  }));
  
  // Sort by time (chronological order)
  pairedData.sort((a, b) => a.time - b.time);
  
  // Extract sorted arrays
  const sortedTimeData = pairedData.map(item => item.time);
  const sortedPercentageData = pairedData.map(item => item.value);
  
  new Chart(canvas, {
    type: 'line',
    data: {
      labels: sortedTimeData,
      datasets: [{
        label: label,
        data: sortedPercentageData,
        borderColor: borderColor,
        backgroundColor: backgroundColor,
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 3,
        pointHoverRadius: 5,
        pointBackgroundColor: borderColor,
        pointBorderColor: '#fff',
        pointBorderWidth: 1
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false
      },
      plugins: {
        legend: {
          display: false
        },
        tooltip: {
          backgroundColor: 'rgba(0, 0, 0, 0.8)',
          titleColor: '#fff',
          bodyColor: '#fff',
          borderColor: borderColor,
          borderWidth: 1,
          padding: 10,
          displayColors: false,
          callbacks: {
            label: function(context) {
              return context.parsed.y.toFixed(2) + '%';
            },
            title: function(context) {
              const date = new Date(context[0].label);
              return date.toLocaleString();
            }
          }
        }
      },
      scales: {
        y: {
          min: 0,
          max: 100,
          ticks: {
            color: '#9CA3AF',
            callback: function(value) {
              return value + '%';
            }
          },
          grid: {
            color: 'rgba(75, 85, 99, 0.3)'
          }
        },
        x: {
          type: 'time',
          time: {
            unit: 'hour',
            displayFormats: {
              hour: 'HH:mm'
            }
          },
          ticks: {
            color: '#9CA3AF',
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8
          },
          grid: {
            color: 'rgba(75, 85, 99, 0.3)'
          }
        }
      }
    }
  });
}

// Format uptime from hundredths of seconds to human-readable format
function formatUptime(hundredthsOfSeconds) {
  // Convert hundredths of seconds to total seconds
  const totalSeconds = Math.floor(hundredthsOfSeconds / 100);
  
  // Calculate days, hours, minutes
  const days = Math.floor(totalSeconds / 86400);
  const hours = Math.floor((totalSeconds % 86400) / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  
  // Build the formatted string
  const parts = [];
  if (days > 0) parts.push(`${days}d`);
  if (hours > 0) parts.push(`${hours}h`);
  if (minutes > 0) parts.push(`${minutes}m`);
  
  return parts.length > 0 ? parts.join(' ') : '0m';
}

// Helper function to escape HTML (if not already defined)
if (typeof escapeHtml === 'undefined') {
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
}
