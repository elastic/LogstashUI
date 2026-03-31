/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Pipeline List - Pagination and Search
// Store state per connection (es_id)
const pipelineStates = {};

// Initialize pipeline list for a connection
function initPipelineList(esId, pipelines) {
    if (!pipelineStates[esId]) {
        pipelineStates[esId] = {
            allPipelines: pipelines,
            currentPage: 1,
            pageSize: 10,
            searchQuery: ''
        };
    } else {
        pipelineStates[esId].allPipelines = pipelines;
    }
    
    // Restore search input value from state (in case the HTML was refreshed)
    const searchInput = document.getElementById(`pipelineSearchInput-${esId}`);
    if (searchInput && pipelineStates[esId].searchQuery) {
        searchInput.value = pipelineStates[esId].searchQuery;
    }
    
    // Set up event listeners
    setupPipelineListeners(esId);
    
    // Initial render
    renderPipelineList(esId);
}

// Set up event listeners for search and pagination
function setupPipelineListeners(esId) {
    const searchInput = document.getElementById(`pipelineSearchInput-${esId}`);
    const pageSizeSelect = document.getElementById(`pipelinePageSize-${esId}`);
    
    if (searchInput && !searchInput.dataset.listenerAttached) {
        let searchTimeout;
        searchInput.addEventListener('input', function(e) {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                pipelineStates[esId].searchQuery = e.target.value.toLowerCase();
                pipelineStates[esId].currentPage = 1;
                renderPipelineList(esId);
            }, 300);
        });
        searchInput.dataset.listenerAttached = 'true';
    }
    
    if (pageSizeSelect && !pageSizeSelect.dataset.listenerAttached) {
        pageSizeSelect.addEventListener('change', function(e) {
            pipelineStates[esId].pageSize = parseInt(e.target.value);
            pipelineStates[esId].currentPage = 1;
            renderPipelineList(esId);
        });
        pageSizeSelect.dataset.listenerAttached = 'true';
    }
}

// Filter pipelines based on search query
function filterPipelines(esId) {
    const state = pipelineStates[esId];
    if (!state) return [];
    
    const query = state.searchQuery;
    if (!query) return state.allPipelines;
    
    return state.allPipelines.filter(pipeline => {
        const nameMatch = pipeline.name.toLowerCase().includes(query);
        const descMatch = pipeline.description && pipeline.description.toLowerCase().includes(query);
        return nameMatch || descMatch;
    });
}

// Render pipeline list with pagination
function renderPipelineList(esId) {
    const state = pipelineStates[esId];
    if (!state) return;
    
    const filteredPipelines = filterPipelines(esId);
    const totalPipelines = filteredPipelines.length;
    const totalPages = Math.ceil(totalPipelines / state.pageSize);
    
    // Adjust current page if needed
    if (state.currentPage > totalPages && totalPages > 0) {
        state.currentPage = totalPages;
    }
    
    // Calculate pagination
    const startIndex = (state.currentPage - 1) * state.pageSize;
    const endIndex = Math.min(startIndex + state.pageSize, totalPipelines);
    const paginatedPipelines = filteredPipelines.slice(startIndex, endIndex);
    
    // Update table body
    const tableBody = document.getElementById(`pipelineTableBody-${esId}`);
    const noResultsDiv = document.getElementById(`pipelineNoResults-${esId}`);
    const pipelineListDiv = document.getElementById(`pipelineList-${esId}`);
    
    if (!tableBody) return;
    
    // Show/hide no results state
    if (filteredPipelines.length === 0) {
        noResultsDiv.classList.remove('hidden');
        pipelineListDiv.classList.add('hidden');
        document.getElementById(`pipelinePagination-${esId}`).classList.add('hidden');
        return;
    } else {
        noResultsDiv.classList.add('hidden');
        pipelineListDiv.classList.remove('hidden');
        document.getElementById(`pipelinePagination-${esId}`).classList.remove('hidden');
    }
    
    // Render pipeline rows
    tableBody.innerHTML = '';
    paginatedPipelines.forEach(pipeline => {
        const row = document.createElement('tr');
        row.innerHTML = `
            <td class="px-4 py-2">
                <a href="/ConnectionManager/Pipelines/Editor/?${pipeline.policy_id ? 'ls_id=' + escapeHtml(pipeline.policy_id) : 'es_id=' + escapeHtml(pipeline.es_id)}&pipeline=${escapeHtml(pipeline.name)}" class="text-blue-500 hover:underline">${escapeHtml(pipeline.name)}</a>
            </td>
            <td class="px-4 py-2 text-gray-300">
                ${pipeline.description ? escapeHtml(pipeline.description).substring(0, 80) + (pipeline.description.length > 80 ? '...' : '') : '<span class="text-gray-500 italic">No description</span>'}
            </td>
            <td class="px-4 py-2 text-gray-300">
                ${pipeline.last_modified || '<span class="text-gray-500 italic">N/A</span>'}
            </td>
            <td class="text-right px-4 py-2">
                <div class="action-menu relative">
                    <button class="action-menu-button p-1 hover:bg-gray-700 rounded">
                        <svg class="h-5 w-5" fill="currentColor" viewBox="0 0 20 20">
                            <path d="M10 6a2 2 0 110-4 2 2 0 010 4zM10 12a2 2 0 110-4 2 2 0 010 4zM10 18a2 2 0 110-4 2 2 0 010 4z" />
                        </svg>
                    </button>
                    <div class="action-menu-items hidden fixed z-50 w-48 bg-gray-800 rounded-md shadow-lg py-1" role="menu" style="transform: translate(-50%, 0);">
                        <div class="px-1 py-1">
                            <button onclick="openCloneModal('${escapeHtml(pipeline.es_id)}', '${escapeHtml(pipeline.name)}')"
                               class="w-full group flex items-center px-4 py-2 text-sm text-blue-400 hover:bg-gray-700 rounded-md"
                               role="menuitem"
                               type="button">
                                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                                </svg>
                                Clone
                            </button>
                            <hr class="my-1 border-gray-700">
                            <button onclick="openRenameModal('${escapeHtml(pipeline.es_id)}', '${escapeHtml(pipeline.name)}')"
                               class="w-full group flex items-center px-4 py-2 text-sm text-yellow-400 hover:bg-gray-700 rounded-md"
                               role="menuitem"
                               type="button">
                                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                                </svg>
                                Rename
                            </button>
                            <hr class="my-1 border-gray-700">
                            <button onclick="openUpdateDescriptionModal('${escapeHtml(pipeline.es_id)}', '${escapeHtml(pipeline.name)}', '${escapeHtml(pipeline.description || '')}')"
                               class="w-full group flex items-center px-4 py-2 text-sm text-purple-400 hover:bg-gray-700 rounded-md"
                               role="menuitem"
                               type="button">
                                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h16m-7 6h7" />
                                </svg>
                                Update Description
                            </button>
                            <hr class="my-1 border-gray-700">
                            <button onclick="deletePipeline('${escapeHtml(pipeline.es_id)}', '${escapeHtml(pipeline.name)}', '${escapeHtml(esId)}', ${pipeline.policy_id ? `'${escapeHtml(pipeline.policy_id)}'` : 'null'})"
                               class="w-full group flex items-center px-4 py-2 text-sm text-red-400 hover:bg-gray-700 rounded-md"
                               role="menuitem"
                               type="button">
                                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                                </svg>
                                Delete
                            </button>
                        </div>
                    </div>
                </div>
            </td>
        `;
        tableBody.appendChild(row);
    });
    
    // Update pagination controls
    updatePipelinePaginationControls(esId, totalPipelines, startIndex, endIndex, totalPages);
    
    // Initialize action menu event listeners after rendering
    if (typeof initActionMenus === 'function') {
        initActionMenus();
    }
}

// Update pagination controls
function updatePipelinePaginationControls(esId, total, startIndex, endIndex, totalPages) {
    const state = pipelineStates[esId];
    
    document.getElementById(`pipelineShowingStart-${esId}`).textContent = total > 0 ? startIndex + 1 : 0;
    document.getElementById(`pipelineShowingEnd-${esId}`).textContent = endIndex;
    document.getElementById(`pipelineTotalCount-${esId}`).textContent = total;
    document.getElementById(`pipelinePageInfo-${esId}`).textContent = `Page ${state.currentPage} of ${totalPages || 1}`;
    
    const prevBtn = document.getElementById(`pipelinePrevBtn-${esId}`);
    const nextBtn = document.getElementById(`pipelineNextBtn-${esId}`);
    
    if (prevBtn) prevBtn.disabled = state.currentPage <= 1;
    if (nextBtn) nextBtn.disabled = state.currentPage >= totalPages;
}

// Pagination functions
function nextPipelinePage(esId) {
    const state = pipelineStates[esId];
    if (!state) return;
    
    const filteredPipelines = filterPipelines(esId);
    const totalPages = Math.ceil(filteredPipelines.length / state.pageSize);
    
    if (state.currentPage < totalPages) {
        state.currentPage++;
        renderPipelineList(esId);
    }
}

function previousPipelinePage(esId) {
    const state = pipelineStates[esId];
    if (!state) return;
    
    if (state.currentPage > 1) {
        state.currentPage--;
        renderPipelineList(esId);
    }
}

// Delete pipeline with confirmation
function deletePipelineFromList(esId, pipelineName) {
    if (!confirm(`Are you sure you want to delete pipeline "${pipelineName}"?`)) {
        return;
    }
    
    const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
    
    fetch('/ConnectionManager/DeletePipeline/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({
            es_id: esId,
            pipeline: pipelineName
        })
    })
    .then(response => {
        if (response.status === 403) {
            throw new Error('Permission denied');
        }
        if (!response.ok) {
            throw new Error('Failed to delete pipeline');
        }
        // Reload the pipeline list
        htmx.ajax('GET', `/ConnectionManager/GetPipelines/${esId}/`, {
            target: `#pipelines-${esId}`,
            swap: 'innerHTML'
        });
    })
    .catch(error => {
        alert('Error deleting pipeline: ' + error.message);
    });
}

// Utility function to escape HTML
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
