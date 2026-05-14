/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

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
      fetch(`/SNMP/GetDeviceVisualization/${deviceId}/`)
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
      
      // Check if official profile (ends with .json)
      const isOfficial = profile.name.endsWith('.json');
      
      // Create friendly display name
      let displayName = profile.name;
      if (isOfficial) {
        // Remove .json extension and convert to title case
        displayName = profile.name.slice(0, -5).replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
      }
      
      // Build metadata line with vendor and product
      let metadata = '';
      if (profile.vendor || profile.product) {
        const parts = [];
        if (profile.vendor) parts.push(escapeHtml(profile.vendor));
        if (profile.product) parts.push(escapeHtml(profile.product));
        metadata = `<div class="text-xs text-gray-400">${parts.join(' • ')}</div>`;
      }
      
      // Official star badge
      const starBadge = isOfficial ? `
        <svg class="w-3 h-3 text-yellow-400 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20">
          <path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.54 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z" />
        </svg>
      ` : '';
      
      profileBadge.innerHTML = `
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
        <div class="flex-1">
          <div class="font-medium flex items-center gap-1.5">
            ${starBadge}
            ${escapeHtml(displayName)}
          </div>
          ${metadata}
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
    const cpuChartCanvas = contentDiv.querySelector('.metric-cpu-chart');
    if (metrics.CPU && metrics.Time && metrics.CPU.length > 0) {
      renderMetricChart(
        cpuChartCanvas,
        metrics.Time,
        metrics.CPU,
        'CPU Usage (%)',
        'rgba(59, 130, 246, 1)', // Blue
        'rgba(59, 130, 246, 0.1)'
      );
    } else if (cpuChartCanvas) {
      // Show message when CPU data is not available
      const chartContainer = cpuChartCanvas.parentElement;
      chartContainer.innerHTML = '<div class="flex items-center justify-center h-full text-gray-400 text-sm italic">Could not find system.cpu.total.norm.pct</div>';
    }

    // Render Memory chart
    const memoryChartCanvas = contentDiv.querySelector('.metric-memory-chart');
    if (metrics.Memory && metrics.Time && metrics.Memory.length > 0) {
      renderMetricChart(
        memoryChartCanvas,
        metrics.Time,
        metrics.Memory,
        'Memory Usage (%)',
        'rgba(16, 185, 129, 1)', // Green
        'rgba(16, 185, 129, 0.1)'
      );
    } else if (memoryChartCanvas) {
      // Show message when Memory data is not available
      const chartContainer = memoryChartCanvas.parentElement;
      chartContainer.innerHTML = '<div class="flex items-center justify-center h-full text-gray-400 text-sm italic">Could not find system.memory.actual.used.pct</div>';
    }
  }

  // Render sensors if available
  if (visualizations && visualizations.sensors) {
    const sensorsSection = contentDiv.querySelector('.device-sensors-section');
    const sensorsContainer = contentDiv.querySelector('.sensors-container');
    // The sensors data is nested in visualizations.sensors.sensors
    const sensorsArray = visualizations.sensors.sensors || [];

    if (sensorsArray.length > 0 && sensorsSection && sensorsContainer) {
      sensorsSection.style.display = 'grid';
      sensorsContainer.innerHTML = '';

      sensorsArray.forEach(sensor => {
        const sensorCard = createSensorCard(sensor);
        sensorsContainer.appendChild(sensorCard);
      });
    } else {
      console.error('Not rendering sensors. Array length:', sensorsArray.length, 'Section:', !!sensorsSection, 'Container:', !!sensorsContainer);
    }
  }

  // Render fans if available
  if (visualizations && visualizations.fans) {
    const sensorsSection = contentDiv.querySelector('.device-sensors-section');
    const fansContainer = contentDiv.querySelector('.fans-container');

    const fansArray = visualizations.fans.fans || [];

    if (fansArray.length > 0 && sensorsSection && fansContainer) {
      sensorsSection.style.display = 'grid';
      fansContainer.innerHTML = '';

      fansArray.forEach(fan => {
        const fanCard = createFanCard(fan);
        fansContainer.appendChild(fanCard);
      });
    }
  }

  // Render interfaces if available
  if (visualizations && visualizations.interfaces) {
    const interfacesSection = contentDiv.querySelector('.device-interfaces-section');
    const interfacesContainer = contentDiv.querySelector('.interfaces-container');

    const interfacesArray = visualizations.interfaces.interfaces || [];

    if (interfacesArray.length > 0 && interfacesSection && interfacesContainer) {
      interfacesSection.style.display = 'block';
      interfacesContainer.innerHTML = '';

      // Sort interfaces by index
      const sortedInterfaces = interfacesArray.sort((a, b) => {
        const indexA = parseInt(a.index) || parseInt(a.ifIndex) || 0;
        const indexB = parseInt(b.index) || parseInt(b.ifIndex) || 0;
        return indexA - indexB;
      });

      sortedInterfaces.forEach(iface => {
        const interfaceCard = createInterfaceCard(iface);
        interfacesContainer.appendChild(interfaceCard);
      });
    }
  }
}

// Create an interface card with status indicators and hover details
function createInterfaceCard(iface) {
  const card = document.createElement('div');

  // Determine status colors based on admin and oper status
  const adminStatus = parseInt(iface.ifAdminStatus);
  const operStatus = parseInt(iface.ifOperStatus);

  // Admin status: 1=Up, 2=Down, 3=Testing
  // Oper status: 1=Up, 2=Down, 3=Testing, 4=Unknown, 5=Dormant, 6=NotPresent, 7=LowerLayerDown

  let borderClass = 'border-gray-600';
  let statusText = 'Unknown';
  let statusColor = 'bg-gray-500';

  if (adminStatus === 2) {
    // Admin down - gray
    borderClass = 'border-gray-500';
    statusText = 'Admin Down';
    statusColor = 'bg-gray-500';
  } else if (adminStatus === 1 && operStatus === 1) {
    // Up/Up - green
    borderClass = 'border-green-500';
    statusText = 'Up';
    statusColor = 'bg-green-500';
  } else if (adminStatus === 1 && operStatus === 2) {
    // Up/Down - red
    borderClass = 'border-red-500';
    statusText = 'Down';
    statusColor = 'bg-red-500';
  } else if (adminStatus === 1 && operStatus === 5) {
    // Dormant - yellow
    borderClass = 'border-yellow-500';
    statusText = 'Dormant';
    statusColor = 'bg-yellow-500';
  } else if (adminStatus === 3 || operStatus === 3) {
    // Testing - blue
    borderClass = 'border-blue-500';
    statusText = 'Testing';
    statusColor = 'bg-blue-500';
  }

  // Format speed
  const speedMbps = iface.ifHighSpeed || (iface.ifSpeed ? iface.ifSpeed / 1000000 : 0);
  const speedText = speedMbps >= 1000 ? `${speedMbps / 1000}G` : `${speedMbps}M`;

  // Format MAC address
  const macAddress = iface.ifPhysAddress || 'N/A';

  // Build detailed tooltip content with better formatting
  const adminStatusText = adminStatus === 1 ? '<span class="text-green-400">Up</span>' : adminStatus === 2 ? '<span class="text-gray-400">Down</span>' : '<span class="text-blue-400">Testing</span>';
  const operStatusHtml = operStatus === 1 ? '<span class="text-green-400">Up</span>' : operStatus === 2 ? '<span class="text-red-400">Down</span>' : `<span class="text-yellow-400">${statusText}</span>`;

  const tooltipContent = `
    <div class="font-semibold text-sm mb-2 pb-2 border-b border-gray-700">${escapeHtml(iface.ifDescr || iface.ifName)}</div>
    ${iface.ifAlias ? `<div class="text-xs text-gray-400 mb-2 italic">${escapeHtml(iface.ifAlias)}</div>` : ''}
    
    <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mb-2">
      <div><span class="text-gray-400">Admin:</span> ${adminStatusText}</div>
      <div><span class="text-gray-400">Oper:</span> ${operStatusHtml}</div>
      <div><span class="text-gray-400">Speed:</span> <span class="text-white">${speedText}</span></div>
      <div><span class="text-gray-400">MTU:</span> <span class="text-white">${iface.ifMtu || 'N/A'}</span></div>
      <div class="col-span-2"><span class="text-gray-400">MAC:</span> <span class="text-white font-mono text-xs">${escapeHtml(macAddress)}</span></div>
    </div>
    
    <div class="border-t border-gray-700 pt-2 mt-2">
      <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div><span class="text-gray-400">Type:</span> <span class="text-white">${iface.ifType || 'N/A'}</span></div>
        <div><span class="text-gray-400">Index:</span> <span class="text-white">${iface.ifIndex || 'N/A'}</span></div>
        <div><span class="text-gray-400">In:</span> <span class="text-green-400">${formatBytes(iface.ifHCInOctets || 0)}</span></div>
        <div><span class="text-gray-400">Out:</span> <span class="text-blue-400">${formatBytes(iface.ifHCOutOctets || 0)}</span></div>
        <div><span class="text-gray-400">In Err:</span> <span class="${iface.ifInErrors > 0 ? 'text-red-400' : 'text-white'}">${iface.ifInErrors || 0}</span></div>
        <div><span class="text-gray-400">Out Err:</span> <span class="${iface.ifOutErrors > 0 ? 'text-red-400' : 'text-white'}">${iface.ifOutErrors || 0}</span></div>
      </div>
    </div>
  `;

  card.className = `relative bg-gray-800 rounded-lg p-1.5 border-2 ${borderClass} hover:shadow-lg transition-all cursor-pointer group`;
  card.innerHTML = `
    <div class="flex flex-col items-center justify-center h-12">
      <div class="w-2.5 h-2.5 rounded-full ${statusColor} mb-1"></div>
      <div class="text-xs font-medium text-white text-center truncate w-full px-0.5">${escapeHtml(iface.ifName || iface.ifDescr)}</div>
      <div class="text-xs text-gray-400 text-xs">${speedText}</div>
    </div>
    
    <!-- Tooltip -->
    <div class="interface-tooltip absolute bottom-full left-0 mb-2 hidden group-hover:block z-50 w-80 pointer-events-none">
      <div class="bg-gray-900 text-white rounded-lg p-3 shadow-2xl border-2 border-gray-600">
        ${tooltipContent}
        <div class="tooltip-arrow absolute top-full left-6 -mt-0.5">
          <div class="border-8 border-transparent border-t-gray-600"></div>
        </div>
      </div>
    </div>
  `;

  // Add hover event to dynamically position tooltip
  card.addEventListener('mouseenter', function() {
    const tooltip = this.querySelector('.interface-tooltip');
    const arrow = this.querySelector('.tooltip-arrow');
    if (tooltip) {
      // Small delay to ensure tooltip is rendered
      setTimeout(() => {
        const tooltipRect = tooltip.getBoundingClientRect();
        const viewportWidth = window.innerWidth;
        
        // Check if tooltip goes off the right edge
        if (tooltipRect.right > viewportWidth) {
          // Switch to right-aligned
          tooltip.classList.remove('left-0');
          tooltip.classList.add('right-0');
          arrow.classList.remove('left-6');
          arrow.classList.add('right-6');
        } else {
          // Keep left-aligned
          tooltip.classList.remove('right-0');
          tooltip.classList.add('left-0');
          arrow.classList.remove('right-6');
          arrow.classList.add('left-6');
        }
      }, 10);
    }
  });

  return card;
}

// Format bytes to human-readable format
function formatBytes(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// Render a metric line chart using D3.js
function renderMetricChart(chartDiv, timeData, metricData, label, borderColor, backgroundColor) {
  if (!chartDiv || !timeData || !metricData) return;

  // Parse ISO timestamp strings to Date objects and create paired data
  const data = timeData.map((timestamp, index) => ({
    time: new Date(timestamp),
    value: metricData[index] * 100  // Convert to percentage
  }));

  // Sort by time (chronological order)
  data.sort((a, b) => a.time - b.time);

  // Clear any existing content and get container dimensions
  const container = chartDiv.parentElement;
  chartDiv.innerHTML = '';
  
  const margin = { top: 10, right: 10, bottom: 40, left: 45 };
  const width = container.clientWidth - margin.left - margin.right;
  const height = container.clientHeight - margin.top - margin.bottom;

  // Create SVG
  const svg = d3.select(chartDiv)
    .append('svg')
    .attr('width', width + margin.left + margin.right)
    .attr('height', height + margin.top + margin.bottom)
    .append('g')
    .attr('transform', `translate(${margin.left},${margin.top})`);

  // Create scales
  const xScale = d3.scaleTime()
    .domain(d3.extent(data, d => d.time))
    .range([0, width]);

  const yScale = d3.scaleLinear()
    .domain([0, 100])
    .range([height, 0]);

  // Create line generator with curve
  const line = d3.line()
    .x(d => xScale(d.time))
    .y(d => yScale(d.value))
    .curve(d3.curveMonotoneX);

  // Create area generator for fill
  const area = d3.area()
    .x(d => xScale(d.time))
    .y0(height)
    .y1(d => yScale(d.value))
    .curve(d3.curveMonotoneX);

  // Add gradient for area fill with unique ID
  const gradientId = `gradient-${Math.random().toString(36).substr(2, 9)}`;
  const defs = svg.append('defs');
  
  const gradient = defs.append('linearGradient')
    .attr('id', gradientId)
    .attr('x1', '0%')
    .attr('y1', '0%')
    .attr('x2', '0%')
    .attr('y2', '100%');

  gradient.append('stop')
    .attr('offset', '0%')
    .attr('stop-color', borderColor)
    .attr('stop-opacity', 0.4);

  gradient.append('stop')
    .attr('offset', '100%')
    .attr('stop-color', borderColor)
    .attr('stop-opacity', 0.05);

  // Add grid lines
  svg.append('g')
    .attr('class', 'grid')
    .attr('opacity', 0.1)
    .call(d3.axisLeft(yScale)
      .tickSize(-width)
      .tickFormat(''));

  // Add area
  svg.append('path')
    .datum(data)
    .attr('fill', `url(#${gradientId})`)
    .attr('d', area);

  // Add line
  svg.append('path')
    .datum(data)
    .attr('fill', 'none')
    .attr('stroke', borderColor)
    .attr('stroke-width', 2)
    .attr('d', line);

  // Add X axis
  const xAxis = d3.axisBottom(xScale)
    .ticks(d3.timeMinute.every(30))
    .tickFormat(d => {
      const hours = d.getHours().toString().padStart(2, '0');
      const mins = d.getMinutes().toString().padStart(2, '0');
      return `${hours}:${mins}`;
    });

  svg.append('g')
    .attr('transform', `translate(0,${height})`)
    .call(xAxis)
    .selectAll('text')
    .style('fill', '#9CA3AF')
    .style('text-anchor', 'end')
    .attr('dx', '-.8em')
    .attr('dy', '.15em')
    .attr('transform', 'rotate(-45)');

  svg.selectAll('.domain, .tick line')
    .style('stroke', 'rgba(75, 85, 99, 0.3)');

  // Add Y axis
  const yAxis = d3.axisLeft(yScale)
    .ticks(5)
    .tickFormat(d => d + '%');

  svg.append('g')
    .call(yAxis)
    .selectAll('text')
    .style('fill', '#9CA3AF');

  svg.selectAll('.domain, .tick line')
    .style('stroke', 'rgba(75, 85, 99, 0.3)');

  // Add tooltip with chart color theme
  const tooltip = d3.select(chartDiv)
    .append('div')
    .style('position', 'absolute')
    .style('background-color', borderColor)
    .style('color', '#fff')
    .style('padding', '8px 12px')
    .style('border-radius', '6px')
    .style('pointer-events', 'none')
    .style('opacity', 0)
    .style('font-size', '12px')
    .style('box-shadow', '0 4px 6px rgba(0, 0, 0, 0.3)')
    .style('z-index', 1000);

  // Add invisible overlay for mouse tracking
  const bisect = d3.bisector(d => d.time).left;
  
  svg.append('rect')
    .attr('width', width)
    .attr('height', height)
    .style('fill', 'none')
    .style('pointer-events', 'all')
    .on('mousemove', function(event) {
      const [mouseX] = d3.pointer(event);
      const x0 = xScale.invert(mouseX);
      const i = bisect(data, x0, 1);
      const d0 = data[i - 1];
      const d1 = data[i];
      const d = d1 && (x0 - d0.time > d1.time - x0) ? d1 : d0;

      if (d) {
        const containerRect = chartDiv.getBoundingClientRect();
        tooltip
          .style('opacity', 0.95)
          .html(`
            <div style="font-weight: bold; margin-bottom: 4px;">${d.time.toLocaleString()}</div>
            <div style="font-size: 14px; font-weight: bold;">${d.value.toFixed(2)}%</div>
          `)
          .style('left', (event.pageX - containerRect.left + 15) + 'px')
          .style('top', (event.pageY - containerRect.top - 10) + 'px');
      }
    })
    .on('mouseout', function() {
      tooltip.style('opacity', 0);
    });
}

// Create a sensor card with temperature gauge
function createSensorCard(sensor) {
  const card = document.createElement('div');

  // Convert Celsius to Fahrenheit
  const tempF = (sensor.temp_celsius * 9 / 5) + 32;

  // Determine state color and label
  const stateInfo = getSensorStateInfo(sensor.state);

  // Calculate percentage for gauge (0 to threshold)
  const percentage = Math.min((sensor.temp_celsius / sensor.temp_threshold) * 100, 100);

  // Calculate Fahrenheit threshold
  const thresholdF = (sensor.temp_threshold * 9 / 5) + 32;

  card.className = 'bg-gray-800 rounded-lg p-3 border-l-4 ' + stateInfo.borderClass;
  card.innerHTML = `
    <div class="flex items-center justify-between mb-2">
      <h4 class="text-sm font-medium text-white truncate">${escapeHtml(sensor.description)}</h4>
      <span class="text-xs px-2 py-1 rounded ${stateInfo.badgeClass}">${stateInfo.label}</span>
    </div>
    
    <!-- Temperature values above gauge -->
    <div class="flex items-center justify-between mb-1">
      <div class="text-2xl font-bold ${stateInfo.textClass}">${tempF.toFixed(1)}°F</div>
      <div class="text-xs text-gray-400">Threshold: ${thresholdF.toFixed(1)}°F</div>
    </div>
    
    <!-- Temperature Gauge -->
    <div class="relative w-full h-2 bg-gray-700 rounded-full overflow-hidden mb-1">
      <div class="absolute h-full ${stateInfo.gaugeClass} transition-all duration-300" 
           style="width: ${percentage}%"></div>
    </div>
    
    <!-- Temperature values below gauge -->
    <div class="flex items-center justify-between">
      <div class="text-sm text-gray-400">${sensor.temp_celsius}°C</div>
      <div class="text-xs text-gray-400">Threshold: ${sensor.temp_threshold}°C</div>
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
    
    <!-- Fan Icon -->
    <div class="flex flex-col items-center justify-center flex-1">
      <svg class="w-12 h-12 ${stateInfo.textClass}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
  switch (parseInt(state)) {
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
