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
      const displayName = profile.display_name || formatDisplayName(profile.name);
      
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
    if (metrics.CPU && metrics.CPUTime && metrics.CPU.length > 0) {
      renderMetricChart(
        cpuChartCanvas,
        metrics.CPUTime,
        metrics.CPU,
        'CPU Usage (%)',
        'rgba(59, 130, 246, 1)', // Blue
        'rgba(59, 130, 246, 0.1)'
      );
    } else if (cpuChartCanvas) {
      // Show message when CPU data is not available
      const chartContainer = cpuChartCanvas.parentElement;
      chartContainer.innerHTML = '<div class="flex items-center justify-center h-full text-gray-400 text-sm italic">No CPU usage data collected for this device</div>';
    }

    // Render Memory chart
    const memoryChartCanvas = contentDiv.querySelector('.metric-memory-chart');
    if (metrics.Memory && metrics.MemoryTime && metrics.Memory.length > 0) {
      // hrStorageRam counts reclaimable cache/buffers, so it reads higher than the
      // normalizer-derived field. Label it rather than passing it off as the same.
      const memoryLabel = metrics.MemorySource === 'hrStorageRam'
        ? 'Memory Usage (%) — incl. cache/buffers'
        : 'Memory Usage (%)';
      renderMetricChart(
        memoryChartCanvas,
        metrics.MemoryTime,
        metrics.Memory,
        memoryLabel,
        'rgba(16, 185, 129, 1)', // Green
        'rgba(16, 185, 129, 0.1)'
      );
    } else if (memoryChartCanvas) {
      // Show message when Memory data is not available
      const chartContainer = memoryChartCanvas.parentElement;
      chartContainer.innerHTML = '<div class="flex items-center justify-center h-full text-gray-400 text-sm italic">No memory usage data collected for this device</div>';
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
        const indexA = parseInt(a.index) || 0;
        const indexB = parseInt(b.index) || 0;
        return indexA - indexB;
      });

      sortedInterfaces.forEach(iface => {
        const interfaceCard = createInterfaceCard(iface);
        interfacesContainer.appendChild(interfaceCard);
      });
    }
  }

  // Render printer supplies if available
  if (visualizations && visualizations.printer_supplies) {
    const suppliesSection = contentDiv.querySelector('.device-printer-supplies-section');
    const suppliesContainer = contentDiv.querySelector('.printer-supplies-container');
    const suppliesArray = visualizations.printer_supplies.supplies || [];

    if (suppliesArray.length > 0 && suppliesSection && suppliesContainer) {
      suppliesSection.style.display = 'block';
      suppliesContainer.innerHTML = '';

      suppliesArray.forEach(supply => {
        const supplyCard = createPrinterSupplyCard(supply);
        suppliesContainer.appendChild(supplyCard);
      });
    }
  }

  // Render filesystems if available
  if (visualizations && visualizations.filesystems) {
    const fsSection = contentDiv.querySelector('.device-filesystems-section');
    const fsContainer = contentDiv.querySelector('.filesystems-container');
    const fsArray = visualizations.filesystems.filesystems || [];

    if (fsArray.length > 0 && fsSection && fsContainer) {
      fsSection.style.display = 'block';
      fsContainer.innerHTML = '';

      fsArray.forEach(fs => {
        const fsCard = createFilesystemCard(fs);
        fsContainer.appendChild(fsCard);
      });
    }
  }

  // Render wireless radios if available
  if (visualizations && visualizations.wireless_radios) {
    const radiosSection = contentDiv.querySelector('.device-wireless-radios-section');
    const radiosContainer = contentDiv.querySelector('.wireless-radios-container');
    const radiosArray = visualizations.wireless_radios.radios || [];

    if (radiosArray.length > 0 && radiosSection && radiosContainer) {
      radiosSection.style.display = 'block';
      radiosContainer.innerHTML = '';

      radiosArray.forEach(radio => {
        const radioCard = createWirelessRadioCard(radio);
        radiosContainer.appendChild(radioCard);
      });
    }
  }

  // Render neighbors if available
  if (visualizations && visualizations.neighbors) {
    const neighborsSection = contentDiv.querySelector('.device-neighbors-section');
    const neighborsContainer = contentDiv.querySelector('.neighbors-container');
    const neighborsArray = visualizations.neighbors.neighbors || [];

    if (neighborsArray.length > 0 && neighborsSection && neighborsContainer) {
      neighborsSection.style.display = 'block';
      neighborsContainer.innerHTML = '';

      neighborsArray.forEach(neighbor => {
        const neighborCard = createNeighborCard(neighbor);
        neighborsContainer.appendChild(neighborCard);
      });
    }
  }

  // Render CPU cores if available
  if (visualizations && visualizations.cpu_cores) {
    const cpuCoresSection = contentDiv.querySelector('.device-cpu-cores-section');
    const cpuCoresContainer = contentDiv.querySelector('.cpu-cores-container');
    const coresArray = visualizations.cpu_cores.cores || [];

    if (coresArray.length > 0 && cpuCoresSection && cpuCoresContainer) {
      cpuCoresSection.style.display = 'block';
      cpuCoresContainer.innerHTML = '';

      coresArray.forEach((core, i) => {
        const coreCard = createCpuCoreCard(core, i);
        cpuCoresContainer.appendChild(coreCard);
      });
    }
  }
}

// Abbreviate common interface name prefixes so port numbers are visible in compact cards.
// The full name is always shown in the hover tooltip.
function abbreviateIfaceName(name) {
  if (!name) return name;
  const prefixes = [
    // Longest/most-specific matches first to avoid partial replacements
    [/^TenGigabitEthernet/i,  'Te'],
    [/^HundredGigE/i,         'Hu'],
    [/^TwentyFiveGigE/i,      '25G'],
    [/^FortyGigabitEthernet/i,'Fo'],
    [/^GigabitEthernet/i,     'Gi'],
    [/^FastEthernet/i,        'Fa'],
    [/^Ethernet/i,            'Eth'],
    [/^Port-channel/i,        'Po'],
    [/^Bundle-Ether/i,        'BE'],
    [/^Loopback/i,            'Lo'],
    [/^Tunnel/i,              'Tu'],
    [/^Serial/i,              'Se'],
    [/^Management/i,          'Mg'],
    [/^Vlan/i,                'Vl'],
    [/^StackSub-St/i,         'StSub'],
    [/^StackPort/i,           'StPo'],
  ];
  for (const [pattern, abbr] of prefixes) {
    if (pattern.test(name)) {
      return name.replace(pattern, abbr);
    }
  }
  return name;
}

// Create an interface card with status indicators and hover details
function createInterfaceCard(iface) {
  const card = document.createElement('div');

  // admin_status / oper_status are stored as strings (UP/DOWN/TESTING/...)
  const adminStatus = iface.admin_status;
  const operStatus  = iface.oper_status;

  let borderClass = 'border-gray-600';
  let statusText = 'Unknown';
  let statusColor = 'bg-gray-500';

  if (adminStatus === 'UP' && operStatus === 'UP') {
    // Admin up / oper up — enabled and active
    borderClass = 'border-green-500';
    statusText = 'Up';
    statusColor = 'bg-green-500';
  } else if (adminStatus === 'DOWN' && operStatus === 'UP') {
    // Admin down / oper up — inconsistent, worth investigating
    borderClass = 'border-yellow-500';
    statusText = 'Admin Down / Link Up';
    statusColor = 'bg-yellow-500';
  } else if (adminStatus === 'UP' && operStatus === 'DORMANT') {
    // Admin up / oper dormant — link enabled but dormant
    borderClass = 'border-yellow-500';
    statusText = 'Dormant';
    statusColor = 'bg-yellow-500';
  } else if (adminStatus === 'TESTING' || operStatus === 'TESTING') {
    // Testing state
    borderClass = 'border-blue-500';
    statusText = 'Testing';
    statusColor = 'bg-blue-500';
  } else {
    // Admin down / oper down, admin up / oper down, or unknown — gray (disabled/no link)
    borderClass = 'border-gray-500';
    statusText = adminStatus === 'DOWN' ? 'Admin Down' : operStatus === 'DOWN' ? 'No Link' : 'Unknown';
    statusColor = 'bg-gray-500';
  }

  const speedMbps = iface.speed_high_mbps ?? (iface.speed ? iface.speed / 1_000_000 : 0);
  const speedText = speedMbps >= 1000 ? `${speedMbps / 1000}G` : `${speedMbps}M`;

  const macAddress = iface.mac ?? 'N/A';

  const ifaceName  = iface.name ?? iface.alt_name ?? '';
  const ifaceAlias = iface.alias ?? '';

  const inBytes  = iface.in_octets  ?? 0;
  const outBytes = iface.out_octets ?? 0;

  const inErrors  = iface.in_errors  ?? 0;
  const outErrors = iface.out_errors ?? 0;

  const mtu   = iface.mtu   ?? 'N/A';
  const type  = iface.type  ?? 'N/A';
  const index = iface.index ?? 'N/A';

  const adminStatusText = adminStatus === 'UP'   ? '<span class="text-green-400">Up</span>'
                        : adminStatus === 'DOWN' ? '<span class="text-gray-400">Down</span>'
                        :                         '<span class="text-blue-400">Testing</span>';
  const operStatusHtml  = operStatus === 'UP'               ? '<span class="text-green-400">Up</span>'
                        : operStatus === 'DOWN'             ? '<span class="text-gray-400">Down</span>'
                        : operStatus === 'LOWER_LAYER_DOWN' ? '<span class="text-orange-400">Lower Layer Down</span>'
                        : operStatus === 'DORMANT'          ? '<span class="text-yellow-400">Dormant</span>'
                        : operStatus === 'NOT_PRESENT'      ? '<span class="text-gray-500">Not Present</span>'
                        :                                     `<span class="text-yellow-400">${escapeHtml(statusText)}</span>`;

  const tooltipContent = `
    <div class="font-semibold text-sm mb-2 pb-2 border-b border-gray-700">${escapeHtml(ifaceName)}</div>
    ${ifaceAlias ? `<div class="text-xs text-gray-400 mb-2 italic">${escapeHtml(ifaceAlias)}</div>` : ''}
    
    <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs mb-2">
      <div><span class="text-gray-400">Admin:</span> ${adminStatusText}</div>
      <div><span class="text-gray-400">Oper:</span> ${operStatusHtml}</div>
      <div><span class="text-gray-400">Speed:</span> <span class="text-white">${speedText}</span></div>
      <div><span class="text-gray-400">MTU:</span> <span class="text-white">${mtu}</span></div>
      <div class="col-span-2"><span class="text-gray-400">MAC:</span> <span class="text-white font-mono text-xs">${escapeHtml(macAddress)}</span></div>
    </div>
    
    <div class="border-t border-gray-700 pt-2 mt-2">
      <div class="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
        <div><span class="text-gray-400">Type:</span> <span class="text-white">${type}</span></div>
        <div><span class="text-gray-400">Index:</span> <span class="text-white">${index}</span></div>
        <div><span class="text-gray-400">In:</span> <span class="text-green-400">${formatBytes(inBytes)}</span></div>
        <div><span class="text-gray-400">Out:</span> <span class="text-blue-400">${formatBytes(outBytes)}</span></div>
        <div><span class="text-gray-400">In Err:</span> <span class="${inErrors > 0 ? 'text-red-400' : 'text-white'}">${inErrors}</span></div>
        <div><span class="text-gray-400">Out Err:</span> <span class="${outErrors > 0 ? 'text-red-400' : 'text-white'}">${outErrors}</span></div>
      </div>
    </div>
  `;

  const displayName = abbreviateIfaceName(ifaceName);

  card.className = `relative bg-gray-800 rounded-lg p-1.5 border-2 ${borderClass} hover:shadow-lg transition-all cursor-pointer group`;
  card.innerHTML = `
    <div class="flex flex-col items-center justify-center h-12">
      <div class="w-2.5 h-2.5 rounded-full ${statusColor} mb-1"></div>
      <div class="text-xs font-medium text-white text-center truncate w-full px-0.5">${escapeHtml(displayName)}</div>
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

// Decode prtMarkerSuppliesSupplyUnit values to labels
function decodePrinterSupplyUnit(unit) {
  const map = {
    3:  'tenths of inches', 4:  'micrometers',   7:  'impressions',
    8:  'sheets',           11: 'hours',          12: 'thousandths of oz',
    13: 'tenths of grams',  14: 'hundredths fl oz', 15: 'tenths of mL',
    16: 'feet',             17: 'meters',         18: 'items',
    19: '%',
  };
  return map[parseInt(unit)] || '';
}

// Infer toner/ink swatch color from the supply description string
function inferSupplyColor(description) {
  if (!description) return null;
  const d = description.toLowerCase();

  if (d.includes('yellow'))  return { swatch: 'bg-yellow-400',  label: 'Yellow',  bar: 'bg-yellow-400',  text: 'text-yellow-400',  border: 'border-yellow-500' };
  if (d.includes('cyan'))    return { swatch: 'bg-cyan-400',    label: 'Cyan',    bar: 'bg-cyan-400',    text: 'text-cyan-400',    border: 'border-cyan-500' };
  if (d.includes('magenta')) return { swatch: 'bg-pink-500',    label: 'Magenta', bar: 'bg-pink-500',    text: 'text-pink-400',    border: 'border-pink-500' };
  if (d.includes('black') || d.includes('toner k')) {
    return { swatch: 'bg-gray-300', label: 'Black', bar: 'bg-gray-400', text: 'text-gray-300', border: 'border-gray-400' };
  }
  if (d.includes('waste'))   return { swatch: 'bg-orange-500', label: 'Waste',  bar: 'bg-orange-500', text: 'text-orange-400', border: 'border-orange-500' };
  if (d.includes('fuser'))   return { swatch: 'bg-purple-500', label: 'Fuser',  bar: 'bg-purple-500', text: 'text-purple-400', border: 'border-purple-500' };
  if (d.includes('drum'))    return { swatch: 'bg-indigo-500', label: 'Drum',   bar: 'bg-indigo-500', text: 'text-indigo-400', border: 'border-indigo-500' };
  return null;
}

// Create a printer supply card with a level gauge and toner-color awareness
function createPrinterSupplyCard(supply) {
  const card = document.createElement('div');

  const level       = typeof supply.level === 'number' ? supply.level : 0;
  const capacityMax = supply.capacity_max || 100;
  const pct         = Math.min(Math.max((level / capacityMax) * 100, 0), 100);
  const pctText     = pct.toFixed(0);
  const unitLabel   = decodePrinterSupplyUnit(supply.unit);

  // Level display: if unit is %, show as %; otherwise show raw level + unit label
  const levelDisplay = unitLabel === '%'
    ? `${pctText}%`
    : `${level}${unitLabel ? ' ' + unitLabel : ''}`;

  const colorInfo = inferSupplyColor(supply.description);

  // If we know the toner color, use it for the bar and border; otherwise fall back to level thresholds
  let barColor, textColor, borderColor;
  if (colorInfo) {
    barColor    = colorInfo.bar;
    textColor   = colorInfo.text;
    borderColor = colorInfo.border;
  } else if (pct <= 10) {
    barColor = 'bg-red-500';    textColor = 'text-red-400';    borderColor = 'border-red-500';
  } else if (pct <= 25) {
    barColor = 'bg-yellow-500'; textColor = 'text-yellow-400'; borderColor = 'border-yellow-500';
  } else {
    barColor = 'bg-emerald-500'; textColor = 'text-emerald-400'; borderColor = 'border-emerald-500';
  }

  // Low-level warning badge regardless of color type
  let warningBadge = '';
  if (pct <= 10) {
    warningBadge = `<span class="text-xs px-1.5 py-0.5 rounded bg-red-600/20 text-red-300 flex-shrink-0">Low</span>`;
  } else if (pct <= 25) {
    warningBadge = `<span class="text-xs px-1.5 py-0.5 rounded bg-yellow-600/20 text-yellow-300 flex-shrink-0">Low</span>`;
  }

  const swatchHtml = colorInfo
    ? `<span class="inline-block w-3 h-3 rounded-sm ${colorInfo.swatch} flex-shrink-0 border border-gray-600"></span>`
    : '';

  card.className = `bg-gray-800 rounded-lg p-3 border-l-4 ${borderColor} w-52 flex-shrink-0`;
  card.innerHTML = `
    <div class="flex items-start justify-between gap-1 mb-2">
      <div class="flex items-center gap-1.5 min-w-0">
        ${swatchHtml}
        <span class="text-xs font-medium text-white truncate" title="${escapeHtml(supply.description)}">${escapeHtml(supply.description)}</span>
      </div>
      ${warningBadge}
    </div>

    <div class="${textColor} text-2xl font-bold leading-none mb-2">${escapeHtml(levelDisplay)}</div>

    <!-- Level gauge -->
    <div class="relative w-full h-2 bg-gray-700 rounded-full overflow-hidden mb-1">
      <div class="absolute h-full ${barColor} transition-all duration-300 rounded-full" style="width: ${pct}%"></div>
    </div>
    <div class="flex justify-between text-xs text-gray-500">
      <span>Empty</span>
      <span>Full</span>
    </div>
  `;

  return card;
}

// Decode HR Storage type OIDs to human-readable labels
function decodeFilesystemType(typeOid) {
  const map = {
    '1.3.6.1.2.1.25.2.1.1':  'Other',
    '1.3.6.1.2.1.25.2.1.2':  'RAM',
    '1.3.6.1.2.1.25.2.1.3':  'Virtual Memory',
    '1.3.6.1.2.1.25.2.1.4':  'Fixed Disk',
    '1.3.6.1.2.1.25.2.1.5':  'Removable Disk',
    '1.3.6.1.2.1.25.2.1.6':  'Floppy Disk',
    '1.3.6.1.2.1.25.2.1.7':  'Compact Disc',
    '1.3.6.1.2.1.25.2.1.8':  'RAM Disk',
    '1.3.6.1.2.1.25.2.1.9':  'Flash Memory',
    '1.3.6.1.2.1.25.2.1.10': 'Network Disk',
  };
  return map[typeOid] || typeOid || 'Unknown';
}

// Create a filesystem card with a capacity gauge
function createFilesystemCard(fs) {
  const card = document.createElement('div');

  const usedPct  = typeof fs.used_pct === 'number' ? fs.used_pct : 0;
  const pct      = Math.min(Math.max(usedPct * 100, 0), 100);
  const pctText  = pct.toFixed(1);
  const freePct  = (100 - pct).toFixed(1);

  const usedBytes  = fs.used_bytes  || 0;
  const totalBytes = fs.total_bytes || 0;
  const freeBytes  = Math.max(totalBytes - usedBytes, 0);

  // Colour thresholds mirroring CPU cores
  let barColor, textColor, borderColor;
  if (pct >= 90) {
    barColor = 'bg-red-500';   textColor = 'text-red-400';    borderColor = 'border-red-500';
  } else if (pct >= 75) {
    barColor = 'bg-yellow-500'; textColor = 'text-yellow-400'; borderColor = 'border-yellow-500';
  } else {
    barColor = 'bg-emerald-500'; textColor = 'text-emerald-400'; borderColor = 'border-emerald-500';
  }

  const typeLabel = decodeFilesystemType(fs.type);

  card.className = `bg-gray-800 rounded-lg p-3 border-l-4 ${borderColor}`;
  card.innerHTML = `
    <div class="flex items-start justify-between gap-2 mb-2">
      <span class="text-sm font-semibold text-white font-mono truncate" title="${escapeHtml(fs.mount_point || '/')}">${escapeHtml(fs.mount_point || '/')}</span>
      <span class="text-xs px-1.5 py-0.5 rounded bg-gray-700 text-gray-300 whitespace-nowrap flex-shrink-0">${escapeHtml(typeLabel)}</span>
    </div>

    <div class="${textColor} text-2xl font-bold leading-none mb-2">${pctText}%</div>

    <!-- Capacity gauge -->
    <div class="relative w-full h-2 bg-gray-700 rounded-full overflow-hidden mb-2">
      <div class="absolute h-full ${barColor} transition-all duration-300 rounded-full" style="width: ${pct}%"></div>
    </div>

    <div class="grid grid-cols-3 gap-1 text-xs">
      <div>
        <span class="text-gray-500 block">Used</span>
        <span class="${textColor} font-mono">${formatBytes(usedBytes)}</span>
      </div>
      <div>
        <span class="text-gray-500 block">Free</span>
        <span class="text-gray-300 font-mono">${formatBytes(freeBytes)}</span>
      </div>
      <div>
        <span class="text-gray-500 block">Total</span>
        <span class="text-gray-300 font-mono">${formatBytes(totalBytes)}</span>
      </div>
    </div>
  `;

  return card;
}

// Map short band codes to human-readable 802.11 standard + frequency labels
function decodeWirelessBand(band) {
  if (!band) return { label: 'Unknown', freq: '', color: 'text-gray-400', badge: 'bg-gray-600/20 text-gray-300' };
  const b = band.toLowerCase();
  const map = {
    'b':    { label: '802.11b',  freq: '2.4 GHz', color: 'text-gray-400',   badge: 'bg-gray-600/20 text-gray-300' },
    'g':    { label: '802.11g',  freq: '2.4 GHz', color: 'text-blue-400',   badge: 'bg-blue-600/20 text-blue-300' },
    'ng':   { label: '802.11n',  freq: '2.4 GHz', color: 'text-blue-400',   badge: 'bg-blue-600/20 text-blue-300' },
    'na':   { label: '802.11n',  freq: '5 GHz',   color: 'text-violet-400', badge: 'bg-violet-600/20 text-violet-300' },
    'a':    { label: '802.11a',  freq: '5 GHz',   color: 'text-violet-400', badge: 'bg-violet-600/20 text-violet-300' },
    'ac':   { label: '802.11ac', freq: '5 GHz',   color: 'text-violet-400', badge: 'bg-violet-600/20 text-violet-300' },
    'ax':   { label: 'Wi-Fi 6',  freq: '6 GHz',   color: 'text-emerald-400','badge': 'bg-emerald-600/20 text-emerald-300' },
    'ax6':  { label: 'Wi-Fi 6E', freq: '6 GHz',   color: 'text-emerald-400','badge': 'bg-emerald-600/20 text-emerald-300' },
    'be':   { label: 'Wi-Fi 7',  freq: '6 GHz',   color: 'text-pink-400',   badge: 'bg-pink-600/20 text-pink-300' },
  };
  return map[b] || { label: band.toUpperCase(), freq: '', color: 'text-blue-400', badge: 'bg-blue-600/20 text-blue-300' };
}

// Create a wireless radio card
function createWirelessRadioCard(radio) {
  const card = document.createElement('div');

  const bandInfo = decodeWirelessBand(radio.band);
  const inBytes     = radio.in_bytes     || 0;
  const outBytes    = radio.out_bytes    || 0;
  const outDiscards = radio.out_discards || 0;
  const outErrors   = radio.out_errors   || 0;
  const hasErrors   = outDiscards > 0 || outErrors > 0;

  card.className = 'bg-gray-800 rounded-lg p-4 border border-gray-600 hover:border-blue-500 transition-colors w-64 flex-shrink-0';
  card.innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <div class="flex items-center gap-2">
        <svg class="w-4 h-4 ${bandInfo.color} flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0" />
        </svg>
        <span class="text-sm font-semibold text-white font-mono">${escapeHtml(radio.name || `Radio ${radio.index}`)}</span>
      </div>
      <span class="text-xs px-2 py-0.5 rounded ${bandInfo.badge}">${bandInfo.label}</span>
    </div>

    <div class="grid grid-cols-2 gap-x-3 gap-y-1.5 text-xs mb-3">
      ${bandInfo.freq ? `
      <div>
        <span class="text-gray-500 block">Frequency</span>
        <span class="${bandInfo.color} font-medium">${bandInfo.freq}</span>
      </div>` : ''}
      ${radio.channel !== '' && radio.channel !== null && radio.channel !== undefined ? `
      <div>
        <span class="text-gray-500 block">Channel</span>
        <span class="text-white font-medium">${escapeHtml(String(radio.channel))}</span>
      </div>` : ''}
    </div>

    <div class="border-t border-gray-700 pt-2 space-y-1 text-xs">
      <div class="flex justify-between">
        <span class="text-gray-500">Rx</span>
        <span class="text-green-400 font-mono">${formatBytes(inBytes)}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-gray-500">Tx</span>
        <span class="text-blue-400 font-mono">${formatBytes(outBytes)}</span>
      </div>
      ${hasErrors ? `
      <div class="flex justify-between">
        <span class="text-gray-500">Tx Discards</span>
        <span class="${outDiscards > 0 ? 'text-yellow-400' : 'text-gray-400'} font-mono">${outDiscards}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-gray-500">Tx Errors</span>
        <span class="${outErrors > 0 ? 'text-red-400' : 'text-gray-400'} font-mono">${outErrors}</span>
      </div>` : ''}
    </div>
  `;

  return card;
}

// Decode CDP/LLDP capabilities hex string (e.g. "00:00:00:28") into human-readable labels
function decodeCdpCapabilities(capHex) {
  if (!capHex) return [];
  // Strip colons and parse as a 32-bit integer
  const hex = capHex.replace(/:/g, '');
  const bits = parseInt(hex, 16);
  if (isNaN(bits)) return [];

  const capMap = [
    [0x0001, 'Router'],
    [0x0002, 'Bridge'],
    [0x0004, 'SR Bridge'],
    [0x0008, 'Switch'],
    [0x0010, 'Host'],
    [0x0020, 'IGMP'],
    [0x0040, 'Repeater'],
    [0x0080, 'VoIP Phone'],
    [0x0100, 'Remotely Managed'],
    [0x0200, 'CVTA'],
    [0x0400, 'Two-Port MAC Relay'],
  ];

  return capMap.filter(([mask]) => bits & mask).map(([, label]) => label);
}

// Create a neighbor card showing CDP/LLDP adjacency details
function createNeighborCard(neighbor) {
  const card = document.createElement('div');

  const caps = decodeCdpCapabilities(neighbor.capabilities);
  const capsBadges = caps.map(c =>
    `<span class="text-xs px-1.5 py-0.5 rounded bg-indigo-600/20 text-indigo-300">${escapeHtml(c)}</span>`
  ).join('');

  // Shorten platform — strip leading vendor word if it duplicates common prefixes
  const platform = neighbor.platform || '';

  // Extract a short OS version line from the multi-line version string
  let versionShort = '';
  if (neighbor.version) {
    const firstLine = neighbor.version.split('\n')[0].trim();
    // Try to pull just the "Version X.Y(Z)" fragment
    const versionMatch = firstLine.match(/Version\s+[\w().]+/i);
    versionShort = versionMatch ? versionMatch[0] : firstLine.slice(0, 60);
  }

  card.className = 'bg-gray-800 rounded-lg p-3 border border-gray-600 hover:border-indigo-500 transition-colors';
  card.innerHTML = `
    <div class="flex items-start justify-between gap-2 mb-2">
      <div class="flex items-center gap-2 min-w-0">
        <svg class="w-4 h-4 text-indigo-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
        </svg>
        <span class="text-sm font-semibold text-white truncate">${escapeHtml(neighbor.device_id || 'Unknown')}</span>
      </div>
      ${neighbor.address ? `<span class="text-xs text-gray-400 font-mono flex-shrink-0">${escapeHtml(neighbor.address)}</span>` : ''}
    </div>

    <div class="space-y-1 text-xs mb-2">
      ${neighbor.port ? `
      <div class="flex items-center gap-1.5">
        <span class="text-gray-500 w-16 flex-shrink-0">Remote Port</span>
        <span class="text-gray-200 font-mono truncate">${escapeHtml(neighbor.port)}</span>
      </div>` : ''}
      ${platform ? `
      <div class="flex items-center gap-1.5">
        <span class="text-gray-500 w-16 flex-shrink-0">Platform</span>
        <span class="text-gray-200 truncate">${escapeHtml(platform)}</span>
      </div>` : ''}
      ${versionShort ? `
      <div class="flex items-center gap-1.5">
        <span class="text-gray-500 w-16 flex-shrink-0">Version</span>
        <span class="text-gray-400 truncate italic">${escapeHtml(versionShort)}</span>
      </div>` : ''}
    </div>

    ${caps.length > 0 ? `
    <div class="flex flex-wrap gap-1 pt-2 border-t border-gray-700">
      ${capsBadges}
    </div>` : ''}
  `;

  return card;
}

// Create a CPU core card with a load percentage gauge and colour-coded utilisation
function createCpuCoreCard(core, displayIndex) {
  const card = document.createElement('div');

  const loadPct = typeof core.load_pct === 'number' ? core.load_pct : 0;
  // load_pct arrives as a fraction (e.g. 0.06 = 6%)
  const pct = Math.min(Math.max(loadPct * 100, 0), 100);
  const pctRounded = pct.toFixed(1);

  // Colour thresholds: green < 60 %, yellow 60–85 %, red > 85 %
  let barColor, textColor, borderColor;
  if (pct >= 85) {
    barColor = 'bg-red-500';
    textColor = 'text-red-400';
    borderColor = 'border-red-500';
  } else if (pct >= 60) {
    barColor = 'bg-yellow-500';
    textColor = 'text-yellow-400';
    borderColor = 'border-yellow-500';
  } else {
    barColor = 'bg-blue-500';
    textColor = 'text-blue-400';
    borderColor = 'border-blue-500';
  }

  card.className = `bg-gray-800 rounded-lg p-3 border-l-4 ${borderColor} w-36 flex-shrink-0`;
  card.innerHTML = `
    <div class="flex items-center justify-between mb-2">
      <span class="text-xs font-semibold text-gray-300 uppercase">Core ${displayIndex}</span>
      <span class="text-xs text-gray-500 font-mono">#${escapeHtml(String(core.index))}</span>
    </div>

    <div class="${textColor} text-2xl font-bold leading-none mb-2">${pctRounded}%</div>

    <!-- Load gauge -->
    <div class="relative w-full h-2 bg-gray-700 rounded-full overflow-hidden">
      <div class="absolute h-full ${barColor} transition-all duration-300" style="width: ${pct}%"></div>
    </div>
    <div class="flex justify-between text-xs text-gray-500 mt-1">
      <span>0%</span>
      <span>100%</span>
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
