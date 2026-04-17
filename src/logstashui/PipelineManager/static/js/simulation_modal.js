/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Store simulation data globally for view switching
window.simulationData = null;

// Line numbers functionality
let logInput;
let logInputLineNumbers;
let multilineCheckbox;
let multilineInputBanner;

function updateLineNumbers(textarea, lineNumbersContainer) {
const lines = textarea.value.split('\n');
const lineCount = lines.length;

// Create a mirror div to measure actual line heights
const mirror = document.createElement('div');
const computedStyle = window.getComputedStyle(textarea);

// Copy relevant styles from textarea to mirror
mirror.style.position = 'absolute';
mirror.style.visibility = 'hidden';
mirror.style.whiteSpace = 'pre-wrap';
mirror.style.wordWrap = 'break-word';
mirror.style.overflowWrap = 'break-word';
// Calculate width minus padding to match actual text area
const paddingLeft = parseFloat(computedStyle.paddingLeft) || 0;
const paddingRight = parseFloat(computedStyle.paddingRight) || 0;
mirror.style.width = (textarea.clientWidth - paddingLeft - paddingRight) + 'px';
mirror.style.font = computedStyle.font;
mirror.style.fontSize = computedStyle.fontSize;
mirror.style.fontFamily = computedStyle.fontFamily;
mirror.style.lineHeight = computedStyle.lineHeight;
mirror.style.padding = '0';
mirror.style.border = 'none';
mirror.style.boxSizing = 'content-box';

document.body.appendChild(mirror);

// Get single line height
mirror.textContent = 'X';
const singleLineHeight = mirror.offsetHeight;

// Generate line numbers with measured heights for each logical line
let lineNumbersHTML = '';
for (let i = 0; i < lineCount; i++) {
  // Set mirror content to this line
  mirror.textContent = lines[i] || ' '; // Use space for empty lines
  const totalLineHeight = mirror.offsetHeight;

  // Create line number that appears at the top of this logical line
  // but takes up the full height so the next line number appears in the right place
  lineNumbersHTML += `<div style="height: ${totalLineHeight}px; line-height: ${singleLineHeight}px;">${i + 1}</div>`;
}

// Clean up mirror
document.body.removeChild(mirror);

lineNumbersContainer.innerHTML = lineNumbersHTML;

// Sync scroll position
lineNumbersContainer.scrollTop = textarea.scrollTop;
}

function updateMultilineBanner() {
const lines = logInput.value.split('\n').filter(line => line.trim() !== '');
if (lines.length > 1 && !multilineCheckbox.checked) {
  multilineInputBanner.classList.remove('hidden');
} else {
  multilineInputBanner.classList.add('hidden');
}
}

// Initialize line numbers and multiline banner when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
  logInput = document.getElementById('logInput');
  logInputLineNumbers = document.getElementById('logInputLineNumbers');
  multilineCheckbox = document.getElementById('multilineCheckbox');
  multilineInputBanner = document.getElementById('multilineInputBanner');

  if (logInput && logInputLineNumbers) {
    logInput.addEventListener('input', () => {
      updateLineNumbers(logInput, logInputLineNumbers);
      updateMultilineBanner();
    });

    logInput.addEventListener('scroll', () => {
      logInputLineNumbers.scrollTop = logInput.scrollTop;
    });

    updateLineNumbers(logInput, logInputLineNumbers);
  }

  if (multilineCheckbox) {
    multilineCheckbox.addEventListener('change', updateMultilineBanner);
  }
});

// Input source switching
function switchInputSource(source) {
const textContainer = document.getElementById('textInputContainer');
const esContainer = document.getElementById('elasticsearchInputContainer');
const logInput = document.getElementById('logInput');
const runBtn = document.getElementById('runSimulationBtn');

if (source === 'text') {
  textContainer.classList.remove('hidden');
  esContainer.classList.add('hidden');
  logInput.required = true;
  runBtn.disabled = false;
} else if (source === 'elasticsearch') {
  textContainer.classList.add('hidden');
  esContainer.classList.remove('hidden');
  logInput.required = false;

  // Load connections
  loadElasticsearchConnections();
}
}

// Load Elasticsearch connections
function loadElasticsearchConnections() {
const select = document.getElementById('esConnection');
fetch('/ConnectionManager/GetElasticsearchConnections/')
  .then(response => response.json())
  .then(data => {
    select.innerHTML = '<option value="">Select a connection...</option>';
    data.connections.forEach(conn => {
      const option = document.createElement('option');
      option.value = conn.id;
      option.textContent = conn.name;
      select.appendChild(option);
    });
    select.disabled = false;
  })
  .catch(error => {
    console.error('Error loading connections:', error);
    select.innerHTML = '<option value="">Error loading connections</option>';
  });
}

// ES Connection change handler
document.addEventListener('DOMContentLoaded', () => {
const esConnection = document.getElementById('esConnection');
if (esConnection) {
  esConnection.addEventListener('change', function() {
    const indexContainer = document.getElementById('esIndexContainer');
    if (this.value) {
      indexContainer.classList.remove('hidden');
      setupIndexTypeahead();
    } else {
      indexContainer.classList.add('hidden');
    }
  });
}
});

// Index typeahead
function setupIndexTypeahead() {
const input = document.getElementById('esIndexInput');
const dropdown = document.getElementById('esIndexDropdown');
const connectionId = document.getElementById('esConnection').value;

let debounceTimer;

input.addEventListener('input', function() {
  clearTimeout(debounceTimer);
  const searchTerm = this.value.trim();

  debounceTimer = setTimeout(() => {
    if (searchTerm.length === 0) {
      // Get top 50 indices
      fetchIndices(connectionId, '*');
    } else {
      // Search with wildcard
      fetchIndices(connectionId, searchTerm + '*');
    }
  }, 300);
});

// Initial load
fetchIndices(connectionId, '*');
}

function fetchIndices(connectionId, pattern) {
const dropdown = document.getElementById('esIndexDropdown');

fetch(`/ConnectionManager/GetElasticsearchIndices/?connection_id=${connectionId}&pattern=${encodeURIComponent(pattern)}`)
  .then(response => response.json())
  .then(data => {
    if (data.indices && data.indices.length > 0) {
      // Clear dropdown and build with DOM methods to avoid XSS
      dropdown.innerHTML = '';
      data.indices.slice(0, 50).forEach(index => {
        const div = document.createElement('div');
        div.className = 'px-3 py-2 hover:bg-gray-600 cursor-pointer text-sm text-white';
        div.textContent = index; // Safe - automatically escapes
        div.onclick = () => selectIndex(index); // Safe - passes as parameter
        dropdown.appendChild(div);
      });
      dropdown.classList.remove('hidden');
    } else {
      dropdown.innerHTML = '<div class="px-3 py-2 text-sm text-gray-400">No indices found</div>';
      dropdown.classList.remove('hidden');
    }
  })
  .catch(error => {
    console.error('Error fetching indices:', error);
    dropdown.innerHTML = '<div class="px-3 py-2 text-sm text-red-400">Error loading indices</div>';
  });
}

function selectIndex(indexName) {
const input = document.getElementById('esIndexInput');
const dropdown = document.getElementById('esIndexDropdown');
const queryMethodContainer = document.getElementById('esQueryMethodContainer');

input.value = indexName;
dropdown.classList.add('hidden');
queryMethodContainer.classList.remove('hidden');

// Load field mappings
loadFieldMappings(indexName);
}

function loadFieldMappings(indexName) {
const connectionId = document.getElementById('esConnection').value;
const fieldSelect = document.getElementById('esField');

fetch(`/ConnectionManager/GetElasticsearchFields/?connection_id=${connectionId}&index=${encodeURIComponent(indexName)}`)
  .then(response => response.json())
  .then(data => {
    fieldSelect.innerHTML = '<option value="">Select a field...</option>';
    data.fields.forEach(field => {
      const option = document.createElement('option');
      option.value = field;
      option.textContent = field;
      fieldSelect.appendChild(option);
    });
  })
  .catch(error => {
    console.error('Error loading fields:', error);
  });
}

// ES Query method switching
function switchEsQueryMethod(method) {
const fieldContainer = document.getElementById('esFieldContainer');
const entireContainer = document.getElementById('esEntireContainer');
const docIdContainer = document.getElementById('esDocIdContainer');

if (method === 'field') {
  fieldContainer.classList.remove('hidden');
  entireContainer.classList.add('hidden');
  docIdContainer.classList.add('hidden');
} else if (method === 'entire') {
  fieldContainer.classList.add('hidden');
  entireContainer.classList.remove('hidden');
  docIdContainer.classList.add('hidden');
} else {
  fieldContainer.classList.add('hidden');
  entireContainer.classList.add('hidden');
  docIdContainer.classList.remove('hidden');
}
}

// Show Elasticsearch preview
function showElasticsearchPreview() {
const connectionId = document.getElementById('esConnection').value;
const index = document.getElementById('esIndexInput').value;
const queryMethod = document.querySelector('input[name="esQueryMethod"]:checked').value;

if (!connectionId || !index) {
  alert('Please select a connection and index first');
  return;
}

// Show preview modal
const previewModal = document.getElementById('previewModal');
const previewContent = document.getElementById('previewContent');
previewModal.classList.remove('hidden');

// Show loading
previewContent.innerHTML = '<div class="flex items-center justify-center py-8"><div class="animate-spin rounded-full h-8 w-8 border-b-2 border-green-400"></div></div>';

// Build request data
let requestData = {
  connection_id: connectionId,
  index: index,
  query_method: queryMethod
};

if (queryMethod === 'field') {
  const field = document.getElementById('esField').value;
  const size = document.getElementById('esSize').value;
  const query = document.getElementById('esQuery').value;

  if (!field) {
    previewContent.innerHTML = '<div class="text-red-400">Please select a field first</div>';
    return;
  }

  requestData.field = field;
  requestData.size = size;
  requestData.query = query;
} else if (queryMethod === 'entire') {
  const size = document.getElementById('esSizeEntire').value;
  const query = document.getElementById('esQueryEntire').value;

  requestData.size = size;
  requestData.query = query;
} else if (queryMethod === 'docid') {
  const docIds = document.getElementById('esDocIds').value;

  if (!docIds.trim()) {
    previewContent.innerHTML = '<div class="text-red-400">Please enter at least one document ID</div>';
    return;
  }

  requestData.doc_ids = docIds;
}

// Fetch preview data
const formData = new FormData();
for (const key in requestData) {
  formData.append(key, requestData[key]);
}

fetch('/ConnectionManager/QueryElasticsearchDocuments/', {
  method: 'POST',
  body: formData,
  headers: {
    'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
  }
})
.then(response => response.json())
.then(data => {
  if (data.error) {
    previewContent.innerHTML = `<div class="text-red-400">Error: ${escapeHtml(data.error)}</div>`;
  } else {
    const documents = data.documents || [];
    if (documents.length === 0) {
      previewContent.innerHTML = '<div class="text-yellow-400">No documents found matching your criteria</div>';
    } else {
      let html = `<div class="text-green-400 mb-4">Found ${documents.length} document(s)</div>`;
      documents.forEach((doc, idx) => {
        html += `<div class="mb-4 pb-4 border-b border-gray-700">`;
        html += `<div class="text-blue-400 font-semibold mb-2">Document ${idx + 1}:</div>`;
        html += `<pre class="whitespace-pre-wrap overflow-x-auto">${JSON.stringify(doc, null, 2)}</pre>`;
        html += `</div>`;
      });
      previewContent.innerHTML = html;
    }
  }
})
.catch(error => {
  previewContent.innerHTML = `<div class="text-red-400">Error fetching preview: ${escapeHtml(error.message)}</div>`;
});
}

function closePreviewModal() {
const previewModal = document.getElementById('previewModal');
previewModal.classList.add('hidden');
}

// Global storage for simulation documents and run IDs
window.simulationDocuments = [];
window.simulationRunIds = [];
window.currentDocumentIndex = 0;

// Intercept form submission to handle both ES and multiline text input
// Wait for DOM to ensure form element exists before attaching event listener
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', attachFormListener);
} else {
  attachFormListener();
}

function attachFormListener() {
  const form = document.getElementById('simulationForm');
  if (form) {
    form.addEventListener('submit', async function(event) {
event.preventDefault();
event.stopPropagation();

// Update status chip to show allocation is starting (for embedded mode)
const statusContainer = document.getElementById('pipelineLoadStatus');
const statusIcon = document.getElementById('pipelineStatusIcon');
const statusMessage = document.getElementById('pipelineStatusMessage');

if (statusContainer && statusIcon && statusMessage) {
    statusContainer.className = 'inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-gray-600 bg-gray-700/50';
    statusIcon.outerHTML = `
        <svg id="pipelineStatusIcon" class="w-4 h-4 animate-spin text-gray-300" fill="currentColor" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
        </svg>
    `;
    statusMessage.className = 'text-xs font-medium text-gray-300';
    statusMessage.textContent = 'Allocating pipeline slot...';
}

// Check if there are any filters in the pipeline
let pipelineComponents;
if (typeof getSubsetComponents === 'function') {
  pipelineComponents = getSubsetComponents();
} else {
  pipelineComponents = typeof components !== 'undefined' ? components : (window.components || {});
}

// Validate that there are filters
if (!pipelineComponents.filter || pipelineComponents.filter.length === 0) {
  if (typeof showToast === 'function') {
    showToast("There aren't any filters in your pipeline. Please add at least one filter and try again.", 'error');
  } else {
    alert("There aren't any filters in your pipeline. Please add at least one filter and try again.");
  }
  return;
}

const inputSource = document.querySelector('input[name="inputSource"]:checked').value;
const logInput = document.getElementById('logInput');
let documents = [];

// Determine documents to simulate
if (inputSource === 'text') {
  const multilineCheckbox = document.getElementById('multilineCheckbox');
  const isMultiline = multilineCheckbox ? multilineCheckbox.checked : false;

  // Check if input has multiple lines
  const lines = logInput.value.split('\n').filter(line => line.trim());
  const hasMultipleLines = lines.length > 1;

  if (hasMultipleLines) {
    // Multiple document mode - treat each line as separate document
    documents = lines.map(line => {
      try {
        return JSON.parse(line);
      } catch {
        return { message: line };
      }
    });
  } else {
    // Single document
    try {
      documents = [JSON.parse(logInput.value)];
    } catch {
      documents = [{ message: logInput.value }];
    }
  }
} else if (inputSource === 'elasticsearch') {
  // Fetch ES documents
  const connection_id = document.getElementById('esConnection').value;
  const index = document.getElementById('esIndexInput').value;
  const query_method = document.querySelector('input[name="esQueryMethod"]:checked').value;

  if (!connection_id || !index) {
    alert('Please select a connection and index');
    return;
  }

  const formData = new FormData();
  formData.append('connection_id', connection_id);
  formData.append('index', index);
  formData.append('query_method', query_method);

  if (query_method === 'field') {
    const field = document.getElementById('esField').value;
    const size = document.getElementById('esSize').value;
    const query = document.getElementById('esQuery').value;
    if (!field) {
      alert('Please select a field');
      return;
    }
    formData.append('field', field);
    formData.append('size', size);
    formData.append('query', query);
  } else if (query_method === 'entire') {
    const size = document.getElementById('esSizeEntire').value;
    const query = document.getElementById('esQueryEntire').value;
    formData.append('size', size);
    formData.append('query', query);
  } else if (query_method === 'docid') {
    const doc_ids = document.getElementById('esDocIds').value;
    if (!doc_ids.trim()) {
      alert('Please enter at least one document ID');
      return;
    }
    formData.append('doc_ids', doc_ids);
  }

  try {
    const response = await fetch('/ConnectionManager/QueryElasticsearchDocuments/', {
      method: 'POST',
      body: formData,
      headers: {
        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
      }
    });

    const data = await response.json();
    if (data.error) {
      alert('Error fetching documents: ' + escapeHtml(data.error));
      return;
    }

    documents = data.documents || [];
    if (documents.length === 0) {
      alert('No documents found matching your criteria in index ' + escapeHtml(index));
      return;
    }
  } catch (error) {
    alert('Error fetching documents: ' + escapeHtml(error.message));
    return;
  }
}

// Store documents globally
window.simulationDocuments = documents;
window.currentDocumentIndex = 0;
window.simulationRunIds = [];

// Submit all documents simultaneously
submitAllDocuments(documents);
    });
  }
}

// Function to submit all documents for simulation simultaneously
async function submitAllDocuments(documents) {
// Create a deep copy of components with file paths updated for simulation
window.simulationComponents = createSimulationComponentsCopy();

// Show toast immediately
showToast('Simulation launched!', 'success');

// Close modal
if (typeof closeSimulationModal === 'function') {
  closeSimulationModal();
}

// Initialize run_ids array
window.simulationRunIds = new Array(documents.length).fill(null);

// Submit all documents and start polling for each
const submissions = documents.map((doc, index) => submitAndPollDocument(doc, index));

// Wait for all submissions to complete
await Promise.all(submissions);
}

// Function to create a deep copy of components with file paths updated for simulation only
function createSimulationComponentsCopy() {
// Get the original components (use subset if in subset mode)
let originalComponents;
if (typeof getSubsetComponents === 'function') {
  originalComponents = getSubsetComponents();
} else {
  originalComponents = typeof components !== 'undefined' ? components : (window.components || {});
}

// Create a deep copy using JSON parse/stringify
const componentsCopy = JSON.parse(JSON.stringify(originalComponents));

// Find all file path inputs in the modal
const filePathInputs = document.querySelectorAll('#filePathPluginList input[type="text"][data-generated-filename]');

// Update the copy with file paths
filePathInputs.forEach(input => {
  const componentId = input.dataset.componentId;
  const optionName = input.dataset.optionName;
  const pluginType = input.dataset.pluginType;
  const generatedFilename = input.dataset.generatedFilename;
  const isIgnored = input.disabled; // If disabled, it's ignored

  if (!componentId || !optionName || !generatedFilename || isIgnored) {
    return; // Skip if missing data or ignored
  }

  // Prepend the logstashagent uploaded directory path
  const fullPath = `/tmp/uploaded/${generatedFilename}`;

  // Find the component by ID in the COPY and update its config
  if (componentsCopy[pluginType]) {
    const component = componentsCopy[pluginType].find(c => c.id === componentId);
    if (component && component.config) {
      // Update the config with the full path in the COPY only
      component.config[optionName] = fullPath;
    }
  }
});

return componentsCopy;
}

// Function to submit a single document, start polling, and return its run_id
async function submitAndPollDocument(doc, index) {
// Use the simulation components copy (with file paths updated)
// This was created in submitAllDocuments and stored in window.simulationComponents
const componentsData = window.simulationComponents;

// Get es_id and pipeline from URL parameters
const esId = new URLSearchParams(window.location.search).get('es_id');
const pipelineName = new URLSearchParams(window.location.search).get('pipeline');

const formData = new FormData();
formData.append('log_text', JSON.stringify(doc));
formData.append('components', JSON.stringify(componentsData));
formData.append('es_id', esId);
formData.append('pipeline', pipelineName);
formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

try {
  const response = await fetch('/ConnectionManager/SimulatePipeline/', {
    method: 'POST',
    body: formData,
    headers: {
      'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
    }
  });

  const html = await response.text();

  // Extract data from response - look for initSimulationResults() call or setAttribute() calls
  // Try to match initSimulationResults('run_id') first
  let runIdMatch = html.match(/initSimulationResults\(['"]([^'"]+)['"]\)/);
  // Also try setAttribute for data-run-id
  if (!runIdMatch) {
    runIdMatch = html.match(/setAttribute\(['"]data-run-id['"],\s*['"]([^'"]+)['"]\)/);
  }
  
  // Extract slot_id from setAttribute call
  const slotIdMatch = html.match(/setAttribute\(['"]data-slot-id['"],\s*['"]([^'"]+)['"]\)/);
  
  // Extract filter count from text content
  const filterCountMatch = html.match(/(\d+)\s+filters/);
  
  if (runIdMatch) {
    const runId = runIdMatch[1];
    const slotId = slotIdMatch ? slotIdMatch[1] : null;
    const filterCount = filterCountMatch ? filterCountMatch[1] : '0';

    // Store run_id BEFORE doing anything else
    window.simulationRunIds[index] = runId;
    
    // Update status chip to show pipeline is ready (for first document only)
    if (index === 0 && slotId) {
      const statusContainer = document.getElementById('pipelineLoadStatus');
      const statusIcon = document.getElementById('pipelineStatusIcon');
      const statusMessage = document.getElementById('pipelineStatusMessage');
      
      if (statusContainer && statusIcon && statusMessage) {
        statusContainer.className = 'inline-flex items-center gap-2 px-3 py-1.5 rounded-full border border-green-600 bg-green-900/30';
        statusIcon.outerHTML = `
          <svg id="pipelineStatusIcon" class="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path>
          </svg>
        `;
        statusMessage.className = 'text-xs font-medium text-green-300';
        statusMessage.textContent = 'Simulation Ready';
      }
    }

    // For first document, show overlay by calling functions directly
    if (index === 0) {
      // Check if Text Mode is selected in the modal
      const viewModeRadio = document.querySelector('input[name="viewMode"]:checked');
      const isTextMode = viewModeRadio && viewModeRadio.value === 'text';
      
      if (isTextMode) {
        // Text Mode: Don't create overlay, keep modal open and show results in modal
        if (typeof initSimulationResults === 'function') {
          initSimulationResults(runId);
        }
      } else {
        // Overlay Mode: Close the modal and create overlay
        createSimulationOverlay(runId, slotId, filterCount);
        
        // Initialize the simulation results polling
        if (typeof initSimulationResults === 'function') {
          initSimulationResults(runId);
        }
      }
    } else {
      // For other documents, just start polling in background
      if (typeof initSimulationResults === 'function') {
        initSimulationResults(runId);
      }
    }

    return runId;
  } else {
    console.error('No run_id found in response for document', index);
    console.error('Response content:', html);
    showToast('Error submitting document ' + (index + 1), 'error');
    return null;
  }
} catch (error) {
  console.error('Error submitting document', index, ':', error);
  return null;
}
}


// Create simulation overlay (replaces eval'd script from template)
function createSimulationOverlay(runId, slotId, filterCount) {
  // Close the modal
  setTimeout(() => {
    if (typeof closeSimulationModal === 'function') {
      closeSimulationModal();
    } else {
      const modal = document.getElementById('simulationModal');
      if (modal) {
        modal.classList.add('hidden');
      }
    }
  }, 100);
  
  // Remove any existing overlay
  const existingOverlay = document.getElementById('simulation-overlay');
  if (existingOverlay) {
    existingOverlay.remove();
  }
  
  // Create and show the overlay
  const overlay = document.createElement('div');
  overlay.id = 'simulation-overlay';
  overlay.className = 'sticky top-0 z-40 bg-gray-900 border-b-2 border-green-500 shadow-lg rounded-lg';
  overlay.style.height = '150px';
  overlay.setAttribute('data-run-id', runId);
  overlay.setAttribute('data-slot-id', slotId);
  
  overlay.innerHTML = `
    <div class="h-full flex flex-col">
      <div class="flex items-center justify-between px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div class="flex items-center gap-3">
          <span class="text-green-400 font-semibold">✓ Simulation Results</span>
          <span class="text-xs text-gray-400">Run ID: ${runId}</span>
          <span id="totalExecutionTime" class="text-xs text-yellow-400 font-semibold" style="display: none;"></span>
          <span class="text-xs text-gray-400">${filterCount} filters</span>
          <div id="documentNavigation" style="display: none;" class="flex items-center gap-2 px-3 py-1 bg-gray-700 rounded-lg">
            <button onclick="previousDocument()" id="prevDocBtn" class="text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed" title="Previous document">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
              </svg>
            </button>
            <span id="documentCounter" class="text-xs text-gray-300 min-w-[60px] text-center">1 / 1</span>
            <button onclick="nextDocument()" id="nextDocBtn" class="text-gray-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed" title="Next document">
              <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path>
              </svg>
            </button>
          </div>
          <div id="simulation-loading-indicator" class="flex items-center gap-2">
            <div class="animate-spin rounded-full h-4 w-4 border-b-2 border-green-400"></div>
            <span class="text-xs text-gray-400">Loading results...</span>
          </div>
          <div id="viewModeSelector" style="display: none;" class="flex items-center gap-3 px-3 py-1 bg-gray-700 rounded-lg">
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="overlayViewMode" value="debugger" checked onchange="switchOverlayView('debugger')" class="text-blue-600 focus:ring-blue-500">
              <span class="text-sm text-gray-300">Overlay</span>
            </label>
            <label class="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="overlayViewMode" value="text" onchange="switchOverlayView('text')" class="text-blue-600 focus:ring-blue-500">
              <span class="text-sm text-gray-300">Text</span>
            </label>
          </div>
        </div>
        <div class="flex items-center gap-2">
          <button onclick="viewSimulationLogs()" 
                  id="viewLogsBtn"
                  class="text-blue-400 hover:text-blue-300 px-3 py-1 rounded hover:bg-gray-700 flex items-center gap-2 text-sm"
                  title="View Logstash logs for this simulation">
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path>
            </svg>
            View Logs
          </button>
          <button onclick="toggleOverlayExpand()" 
                  id="expandOverlayBtn"
                  class="text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-700"
                  title="Expand to full screen">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"></path>
            </svg>
          </button>
          <button onclick="cleanupSimulation()" 
                  class="text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-700">
            ✕ Close
          </button>
        </div>
      </div>
      <div id="results-container" class="flex-1 bg-gray-900 overflow-x-auto overflow-y-hidden">
        <svg id="pipeline-graph" width="100%" height="100" class="bg-gray-900"></svg>
      </div>
      <div id="textViewContainer" style="display: none;" class="flex-1 bg-gray-900 overflow-y-auto p-4">
        <div id="textViewContent" class="space-y-4 font-mono text-sm">
          <!-- Text view will be populated here -->
        </div>
      </div>
    </div>
  `;
  
  // Insert overlay at the beginning of the content area (after navigation)
  const contentArea = document.querySelector('main') || document.querySelector('.container') || document.body;
  if (contentArea.firstChild) {
    contentArea.insertBefore(overlay, contentArea.firstChild);
  } else {
    contentArea.appendChild(overlay);
  }
}

// Listen for simulation data updates and display in text mode if selected
window.addEventListener('simulationDataReady', function(event) {
const viewMode = document.querySelector('input[name="viewMode"]:checked');
if (viewMode && viewMode.value === 'text') {
  const textViewContainer = document.getElementById('textViewContainerModal');
  if (textViewContainer && event.detail) {
    textViewContainer.style.display = 'block';
    generateTextViewModal(event.detail);
  }
}
});

function generateTextViewModal(data) {
const textViewContent = document.getElementById('textViewContentModal');
if (!textViewContent || !data.nodes) return;

const html = window.generateTextView ? window.generateTextView(data) : '';
textViewContent.innerHTML = html;
}

function clearSimulationResults() {
const resultsDiv = document.getElementById('simulationResults');
if (resultsDiv) resultsDiv.innerHTML = '';

const textView = document.getElementById('textViewContentModal');
if (textView) textView.innerHTML = '';

window.simulationData = null;
}

function closeSimulationModal() {
const modal = document.getElementById('simulationModal');
if (modal) modal.classList.add('hidden');
}

function openSimulationModal() {
const modal = document.getElementById('simulationModal');
if (modal) {
    modal.classList.remove('hidden');
    
    // Trigger custom event for slot preallocation
    // This allows the pipeline to warm up when the modal opens
    const slotPreallocation = document.getElementById('slotPreallocation');
    if (slotPreallocation) {
        htmx.trigger(slotPreallocation, 'simulationModalOpened');
    }
}
}

window.addEventListener('beforeunload', clearSimulationResults);
document.addEventListener('visibilitychange', function() {
if (document.hidden) clearSimulationResults();
});