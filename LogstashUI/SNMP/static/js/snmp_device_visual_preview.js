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
  
  // Populate device configuration
  clone.querySelector('.device-port').textContent = device.port;
  clone.querySelector('.device-timeout').textContent = `${device.timeout}ms`;
  clone.querySelector('.device-retries').textContent = device.retries;
  
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
  
  // Render sensors if available
  if (visualizations && visualizations.sensors) {
    console.log('Sensors data found:', visualizations.sensors);
    console.log('Sensors array:', visualizations.sensors.sensors);
    const sensorsSection = contentDiv.querySelector('.device-sensors-section');
    const sensorsContainer = contentDiv.querySelector('.sensors-container');
    
    console.log('Sensors section element:', sensorsSection);
    console.log('Sensors container element:', sensorsContainer);
    
    // The sensors data is nested in visualizations.sensors.sensors
    const sensorsArray = visualizations.sensors.sensors || [];
    console.log('Actual sensors array:', sensorsArray);
    
    if (sensorsArray.length > 0 && sensorsSection && sensorsContainer) {
      console.log('Rendering', sensorsArray.length, 'sensors');
      sensorsSection.style.display = 'grid';
      sensorsContainer.innerHTML = '';
      
      sensorsArray.forEach(sensor => {
        console.log('Creating card for sensor:', sensor);
        const sensorCard = createSensorCard(sensor);
        sensorsContainer.appendChild(sensorCard);
      });
    } else {
      console.log('Not rendering sensors. Array length:', sensorsArray.length, 'Section:', !!sensorsSection, 'Container:', !!sensorsContainer);
    }
  }
  
  // Render fans if available
  if (visualizations && visualizations.fans) {
    console.log('Fans data found:', visualizations.fans);
    const sensorsSection = contentDiv.querySelector('.device-sensors-section');
    const fansContainer = contentDiv.querySelector('.fans-container');
    
    const fansArray = visualizations.fans.fans || [];
    console.log('Actual fans array:', fansArray);
    
    if (fansArray.length > 0 && sensorsSection && fansContainer) {
      console.log('Rendering', fansArray.length, 'fans');
      sensorsSection.style.display = 'grid';
      fansContainer.innerHTML = '';
      
      fansArray.forEach(fan => {
        console.log('Creating card for fan:', fan);
        const fanCard = createFanCard(fan);
        fansContainer.appendChild(fanCard);
      });
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
          type: 'timeseries',
          time: {
            unit: 'hour',
            tooltipFormat: 'MMM dd yyyy, HH:mm',
            displayFormats: {
              hour: 'MMM dd HH:mm',
              minute: 'HH:mm'
            }
          },
          ticks: {
            color: '#9CA3AF',
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8,
            source: 'auto'
          },
          grid: {
            color: 'rgba(75, 85, 99, 0.3)'
          }
        }
      }
    }
  });
}

// Create a sensor card with temperature gauge
function createSensorCard(sensor) {
  const card = document.createElement('div');
  
  // Convert Celsius to Fahrenheit
  const tempF = (sensor.temp_celsius * 9/5) + 32;
  
  // Determine state color and label
  const stateInfo = getSensorStateInfo(sensor.state);
  
  // Calculate percentage for gauge (0 to threshold)
  const percentage = Math.min((sensor.temp_celsius / sensor.temp_threshold) * 100, 100);
  
  card.className = 'bg-gray-800 rounded-lg p-3 border-l-4 ' + stateInfo.borderClass;
  card.innerHTML = `
    <div class="flex items-center justify-between mb-2">
      <h4 class="text-sm font-medium text-white truncate">${escapeHtml(sensor.description)}</h4>
      <span class="text-xs px-2 py-1 rounded ${stateInfo.badgeClass}">${stateInfo.label}</span>
    </div>
    
    <!-- Temperature Display -->
    <div class="flex items-center justify-between mb-2">
      <div class="text-2xl font-bold ${stateInfo.textClass}">${sensor.temp_celsius}°C</div>
      <div class="text-sm text-gray-400">${tempF.toFixed(1)}°F</div>
    </div>
    
    <!-- Temperature Gauge -->
    <div class="relative w-full h-2 bg-gray-700 rounded-full overflow-hidden mb-1">
      <div class="absolute h-full ${stateInfo.gaugeClass} transition-all duration-300" 
           style="width: ${percentage}%"></div>
    </div>
    
    <!-- Threshold Label -->
    <div class="text-xs text-gray-400 text-right">
      Threshold: ${sensor.temp_threshold}°C
    </div>
  `;
  
  return card;
}

// Create a fan card with state display
function createFanCard(fan) {
  const card = document.createElement('div');
  
  // Determine state color and label
  const stateInfo = getSensorStateInfo(fan.state);
  
  // Determine if fan should be spinning (normal or warning states)
  const isOperational = parseInt(fan.state) === 1 || parseInt(fan.state) === 2;
  
  card.className = 'bg-gray-800 rounded-lg p-3 border-l-4 min-h-[160px] flex flex-col ' + stateInfo.borderClass;
  card.innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <h4 class="text-sm font-medium text-white truncate">${escapeHtml(fan.description)}</h4>
      <span class="text-xs px-2 py-1 rounded ${stateInfo.badgeClass}">${stateInfo.label}</span>
    </div>
    
    <!-- Fan Icon with State-based Animation -->
    <div class="flex flex-col items-center justify-center flex-1">
      <svg class="w-16 h-16 ${stateInfo.textClass} ${isOperational ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24" style="animation-duration: ${isOperational ? '2s' : '0s'}">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
      </svg>
      <div class="text-xs text-gray-400 mt-2 text-center">
        ${isOperational ? 'Operational' : 'Not Running'}
      </div>
    </div>
  `;
  
  return card;
}

// Get sensor/fan state information (color, label, etc.)
function getSensorStateInfo(state) {
  switch(parseInt(state)) {
    case 1: // Normal
      return {
        label: 'Normal',
        borderClass: 'border-green-500',
        badgeClass: 'bg-green-600/20 text-green-300',
        textClass: 'text-green-400',
        gaugeClass: 'bg-green-500'
      };
    case 2: // Warning
      return {
        label: 'Warning',
        borderClass: 'border-yellow-500',
        badgeClass: 'bg-yellow-600/20 text-yellow-300',
        textClass: 'text-yellow-400',
        gaugeClass: 'bg-yellow-500'
      };
    case 3: // Critical
      return {
        label: 'Critical',
        borderClass: 'border-red-500',
        badgeClass: 'bg-red-600/20 text-red-300',
        textClass: 'text-red-400',
        gaugeClass: 'bg-red-500'
      };
    case 4: // Shutdown
      return {
        label: 'Shutdown',
        borderClass: 'border-red-700',
        badgeClass: 'bg-red-700/20 text-red-400',
        textClass: 'text-red-500',
        gaugeClass: 'bg-red-700'
      };
    case 5: // Not Present
      return {
        label: 'Not Present',
        borderClass: 'border-gray-500',
        badgeClass: 'bg-gray-600/20 text-gray-300',
        textClass: 'text-gray-400',
        gaugeClass: 'bg-gray-500'
      };
    case 6: // Not Functioning
      return {
        label: 'Not Functioning',
        borderClass: 'border-orange-500',
        badgeClass: 'bg-orange-600/20 text-orange-300',
        textClass: 'text-orange-400',
        gaugeClass: 'bg-orange-500'
      };
    default:
      return {
        label: 'Unknown',
        borderClass: 'border-gray-500',
        badgeClass: 'bg-gray-600/20 text-gray-300',
        textClass: 'text-gray-400',
        gaugeClass: 'bg-gray-500'
      };
  }
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
