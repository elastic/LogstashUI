/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

document.addEventListener('DOMContentLoaded', function() {
    const tabButtons = document.querySelectorAll('button[data-tab]');
    const pasteTab = document.getElementById('pasteTab');
    const uploadTab = document.getElementById('uploadTab');
    const logInput = document.getElementById('logInput');
    const logFile = document.getElementById('logFile');
    const form = document.getElementById('integrationForm');
    const classificationArea = document.getElementById('classificationArea');
    const classificationResult = document.getElementById('classificationResult');
    const pipelineTypeSelection = document.getElementById('pipelineTypeSelection');
    const pipelineArea = document.getElementById('pipelineArea');
    const pipelineOutput = document.getElementById('pipelineOutput');
    const generateBtn = document.getElementById('generateBtn');
    const elasticsearchPipelineBtn = document.getElementById('elasticsearchPipelineBtn');
    const logstashPipelineBtn = document.getElementById('logstashPipelineBtn');
    
    let classificationData = null;
    const connectionSelect = document.getElementById('connectionSelect');
    const modelSelectContainer = document.getElementById('modelSelectContainer');
    const logInputContainer = document.getElementById('logInputContainer');
    const modelSelect = document.getElementById('modelSelect');
    const modelHint = document.getElementById('modelHint');

    // Timer functionality
    const timer = document.getElementById('timer');
    const timerDisplay = document.getElementById('timerDisplay');
    const pauseTimerBtn = document.getElementById('pauseTimer');
    const resetTimerBtn = document.getElementById('resetTimer');
    let timerInterval = null;
    let timerSeconds = 0;
    let timerPaused = false;

    function updateTimerDisplay() {
        const minutes = Math.floor(timerSeconds / 60);
        const seconds = timerSeconds % 60;
        timerDisplay.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    }

    function startTimer() {
        if (!timerInterval) {
            timer.classList.remove('hidden');
            timerInterval = setInterval(() => {
                if (!timerPaused) {
                    timerSeconds++;
                    updateTimerDisplay();
                }
            }, 1000);
        }
    }

    function pauseTimer() {
        timerPaused = !timerPaused;
        if (timerPaused) {
            pauseTimerBtn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>`;
        } else {
            pauseTimerBtn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>`;
        }
    }

    function stopTimer() {
        if (timerInterval) {
            clearInterval(timerInterval);
            timerInterval = null;
            timerPaused = true;
        }
    }

    function resetTimer() {
        timerSeconds = 0;
        timerPaused = false;
        updateTimerDisplay();
        pauseTimerBtn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 9v6m4-6v6m7-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>`;
    }

    pauseTimerBtn.addEventListener('click', pauseTimer);
    resetTimerBtn.addEventListener('click', resetTimer);

    connectionSelect.addEventListener('change', async function() {
        const connectionId = this.value;
        
        if (!connectionId) return;
        
        // Start the timer when connection is selected
        startTimer();
        
        modelSelectContainer.classList.remove('hidden');
        modelSelect.disabled = true;
        modelSelect.innerHTML = '<option value="" disabled selected>Loading models...</option>';
        modelHint.textContent = 'Loading available models...';
        
        try {
            const response = await fetch(`${window.location.origin}/AI/IntegrationFactory/models/?connection_id=${connectionId}`);
            const data = await response.json();
            
            console.log('Backend response:', data);
            
            if (data.error) {
                modelSelect.innerHTML = '<option value="" disabled selected>Error loading models</option>';
                modelHint.textContent = `Error: ${data.error}`;
                modelHint.classList.add('text-error');
                return;
            }
            
            if (data.models && data.models.length > 0) {
                modelSelect.innerHTML = '<option value="" disabled selected>Select a model...</option>';
                
                // Deduplicate models by name (keep first occurrence of each unique name)
                const seenNames = new Set();
                const uniqueModels = data.models.filter(model => {
                    const modelName = model.name || model.inference_id;
                    if (seenNames.has(modelName)) {
                        return false;
                    }
                    seenNames.add(modelName);
                    return true;
                });
                
                // Sort models: prioritize Claude Sonnet 4.6 at the top
                const sortedModels = [...uniqueModels].sort((a, b) => {
                    const aName = (a.name || a.inference_id).toLowerCase();
                    const bName = (b.name || b.inference_id).toLowerCase();
                    
                    // Check if either is Claude Sonnet 4.6
                    const aIsClaude46 = aName.includes('claude') && aName.includes('sonnet') && aName.includes('4.6');
                    const bIsClaude46 = bName.includes('claude') && bName.includes('sonnet') && bName.includes('4.6');
                    
                    if (aIsClaude46 && !bIsClaude46) return -1;
                    if (!aIsClaude46 && bIsClaude46) return 1;
                    
                    // Otherwise maintain original order
                    return 0;
                });
                
                sortedModels.forEach(model => {
                    const option = document.createElement('option');
                    option.value = model.inference_id;
                    const modelName = model.name || model.inference_id;
                    const modelNameLower = modelName.toLowerCase();
                    
                    // Add star if it's Claude Sonnet 4.6
                    const isClaude46 = modelNameLower.includes('claude') && 
                                      modelNameLower.includes('sonnet') && 
                                      modelNameLower.includes('4.6');
                    
                    option.textContent = isClaude46 ? `⭐ ${modelName}` : modelName;
                    modelSelect.appendChild(option);
                });
                
                modelSelect.disabled = false;
                modelHint.textContent = `Found ${sortedModels.length} available models`;
                modelHint.classList.remove('text-error');
            } else {
                modelSelect.innerHTML = '<option value="" disabled selected>No completion models found</option>';
                modelHint.textContent = 'No completion-type inference models available on this connection';
                modelHint.classList.add('text-error');
            }
        } catch (error) {
            modelSelect.innerHTML = '<option value="" disabled selected>Error loading models</option>';
            modelHint.textContent = `Error: ${error.message}`;
            modelHint.classList.add('text-error');
        }
    });

    // Show log input container when model is selected
    modelSelect.addEventListener('change', function() {
        if (this.value) {
            logInputContainer.classList.remove('hidden');
        }
    });

    // Handle tab switching
    tabButtons.forEach(button => {
        button.addEventListener('click', function(e) {
            e.preventDefault();
            tabButtons.forEach(btn => btn.classList.remove('tab-active'));
            this.classList.add('tab-active');
            
            const tabType = this.dataset.tab;
            if (tabType === 'paste') {
                pasteTab.classList.remove('hidden');
                uploadTab.classList.add('hidden');
                logInput.required = true;
                logFile.required = false;
            } else {
                pasteTab.classList.add('hidden');
                uploadTab.classList.remove('hidden');
                logInput.required = false;
                logFile.required = true;
            }
        });
    });

    // Step 1: Classify logs
    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        
        const formData = new FormData(form);
        
        generateBtn.disabled = true;
        generateBtn.classList.add('opacity-50', 'cursor-not-allowed');
        classificationArea.classList.remove('hidden');
        classificationResult.innerHTML = '<div class="text-center py-4"><span class="loading loading-spinner loading-lg"></span><p class="mt-2 text-gray-400">Analyzing your logs...</p></div>';
        pipelineTypeSelection.classList.add('hidden');

        try {
            const response = await fetch(`${window.location.origin}/AI/IntegrationFactory/classify/`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Classification failed');
            }

            classificationData = await response.json();
            
            // Display classification result
            const hasIntegration = classificationData.has_integration;
            // Always use Loggy image for both prebuilt and custom integrations
            
            // Parse the message for custom integrations
            let descriptionText = '';
            let callToAction = '';
            let reasonText = '';
            
            if (!hasIntegration && classificationData.message) {
                const message = classificationData.message;
                
                // Split on "Let's build a custom integration!"
                const parts = message.split("Let's build a custom integration!");
                if (parts.length >= 2) {
                    descriptionText = parts[0].trim();
                    callToAction = "Let's build a custom integration!";
                    
                    // Extract reason if present
                    const reasonMatch = parts[1].match(/Reason:\s*(.+)/);
                    if (reasonMatch) {
                        reasonText = reasonMatch[1].trim();
                    }
                } else {
                    descriptionText = message;
                }
            }
            
            classificationResult.innerHTML = `
                <div class="flex items-center gap-4 mb-3">
                    <img src="/static/images/LoggyWizardIcon.png" alt="Loggy Wizard" class="h-16 w-auto flex-shrink-0 drop-shadow-lg" />
                    <div class="flex-1">
                        ${hasIntegration ? `
                            <p class="text-white font-semibold mb-3">${classificationData.message}</p>
                            <div class="text-sm text-gray-400">
                                <p><strong>Integration:</strong> ${classificationData.integration_name}</p>
                            </div>
                        ` : `
                            <p class="text-gray-300 italic mb-2">${descriptionText}</p>
                            <p class="text-white font-bold mb-3">${callToAction}</p>
                            <div class="text-sm text-gray-400">
                                <div class="flex items-center gap-2">
                                    <span><strong>Dataset:</strong> ${classificationData.integration_name}</span>
                                    ${reasonText ? `
                                        <span class="tooltip tooltip-right inline-flex" data-tip="${escapeHtml(reasonText)}">
                                            <svg class="w-4 h-4 text-gray-500 cursor-help" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                                            </svg>
                                        </span>
                                    ` : ''}
                                </div>
                            </div>
                        `}
                    </div>
                </div>
            `;
            
            // Update pipeline type selection based on integration availability
            if (hasIntegration) {
                // Show import button, hide pipeline type selection initially
                pipelineTypeSelection.innerHTML = `
                    <h4 class="text-md font-semibold text-white mb-3">Import Integration</h4>
                    <button id="importPrebuiltBtn" class="btn btn-primary w-full mb-3">
                        <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                        Import Prebuilt Assets
                    </button>
                    <div class="text-center">
                        <a href="#" id="showCustomIntegrationLink" class="text-sm text-blue-400 hover:text-blue-300 underline">
                            Create custom integration anyway
                        </a>
                    </div>
                    <div id="customPipelineButtons" class="hidden mt-4">
                        <h4 class="text-md font-semibold text-white mb-3">Select Pipeline Type</h4>
                        <div class="flex gap-4">
                            <button id="elasticsearchPipelineBtn2" type="button" class="btn btn-primary flex-1">
                                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                                </svg>
                                Elasticsearch Ingest Pipeline
                            </button>
                            <button id="logstashPipelineBtn2" type="button" class="btn btn-secondary flex-1 opacity-50 cursor-not-allowed" disabled>
                                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                                </svg>
                                Logstash Pipeline <span class="text-xs ml-1">(Coming Soon!)</span>
                            </button>
                        </div>
                    </div>
                `;
                
                // Add event listener for Import Prebuilt Assets button
                setTimeout(() => {
                    const importBtn = document.getElementById('importPrebuiltBtn');
                    const showCustomLink = document.getElementById('showCustomIntegrationLink');
                    const customButtons = document.getElementById('customPipelineButtons');
                    const elasticsearchBtn2 = document.getElementById('elasticsearchPipelineBtn2');
                    
                    if (importBtn) {
                        importBtn.addEventListener('click', () => installPrebuiltIntegration());
                    }
                    
                    if (showCustomLink) {
                        showCustomLink.addEventListener('click', (e) => {
                            e.preventDefault();
                            customButtons.classList.remove('hidden');
                            showCustomLink.style.display = 'none';
                        });
                    }
                    
                    if (elasticsearchBtn2) {
                        elasticsearchBtn2.addEventListener('click', () => generatePipeline('elasticsearch'));
                    }
                }, 0);
            } else {
                // Show pipeline type selection for custom integrations
                pipelineTypeSelection.innerHTML = `
                    <h4 class="text-md font-semibold text-white mb-3">Select Pipeline Type</h4>
                    <div class="flex gap-4">
                        <button id="elasticsearchPipelineBtn2" type="button" class="btn btn-primary flex-1">
                            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                            </svg>
                            Elasticsearch Ingest Pipeline
                        </button>
                        <button id="logstashPipelineBtn2" type="button" class="btn btn-secondary flex-1 opacity-50 cursor-not-allowed" disabled>
                            <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                            </svg>
                            Logstash Pipeline <span class="text-xs ml-1">(Coming Soon!)</span>
                        </button>
                    </div>
                `;
                
                // Add event listener for Elasticsearch button
                setTimeout(() => {
                    const elasticsearchBtn2 = document.getElementById('elasticsearchPipelineBtn2');
                    if (elasticsearchBtn2) {
                        elasticsearchBtn2.addEventListener('click', () => generatePipeline('elasticsearch'));
                    }
                }, 0);
            }
            
            pipelineTypeSelection.classList.remove('hidden');
            
        } catch (error) {
            classificationResult.innerHTML = `<div class="alert alert-error"><span>Error: ${error.message}</span></div>`;
        } finally {
            generateBtn.disabled = false;
            generateBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        }
    });

    // Step 2: Generate pipeline with progressive updates
    async function generatePipeline(pipelineType) {
        // If logstash pipeline, do nothing
        if (pipelineType === 'logstash') {
            console.log('Logstash pipeline generation not implemented yet');
            return;
        }
        
        const formData = new FormData(form);
        formData.append('classification', JSON.stringify(classificationData));
        formData.append('pipeline_type', pipelineType);
        
        pipelineArea.classList.remove('hidden');
        pipelineOutput.innerHTML = '<div class="space-y-4" id="progressContainer"></div>';
        
        // Add initial loading indicator
        const progressContainer = document.getElementById('progressContainer');
        addLoadingCard(progressContainer, 'initial-loading', 'Analyzing logs and generating pipeline...');
        
        // Disable both buttons
        elasticsearchPipelineBtn.disabled = true;
        elasticsearchPipelineBtn.classList.add('opacity-50', 'cursor-not-allowed');
        logstashPipelineBtn.disabled = true;
        logstashPipelineBtn.classList.add('opacity-50', 'cursor-not-allowed');

        try {
            const response = await fetch(`${window.location.origin}/AI/IntegrationFactory/generate/`, {
                method: 'POST',
                body: formData
            });

            if (!response.ok) {
                throw new Error('Pipeline generation failed');
            }

            // Read streaming response line by line
            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                
                buffer += decoder.decode(value, { stream: true });
                const lines = buffer.split('\n');
                buffer = lines.pop(); // Keep incomplete line in buffer
                
                for (const line of lines) {
                    if (line.trim()) {
                        const data = JSON.parse(line);
                        handleProgressUpdate(data);
                    }
                }
            }
            
        } catch (error) {
            pipelineOutput.innerHTML = `<div class="alert alert-error"><span>Error: ${error.message}</span></div>`;
        } finally {
            elasticsearchPipelineBtn.disabled = false;
            logstashPipelineBtn.disabled = false;
        }
    }

    function handleProgressUpdate(data) {
        const container = document.getElementById('progressContainer');
        
        if (data.step === 'verified') {
            // Remove all loading cards
            removeLoadingCard(container, 'initial-loading');
            removeLoadingCard(container, 'generating-loading');
            removeLoadingCard(container, 'verifying-loading');
            
            // Merged card: Pipeline Generated and Verified with Documents
            const attempts = data.attempts || 1;
            
            // Extract parsed documents from simulation results
            let parsedDocuments = [];
            if (data.simulation_results && data.simulation_results.docs) {
                parsedDocuments = data.simulation_results.docs
                    .map(doc => {
                        // Handle different possible structures from Elasticsearch simulation API
                        if (doc?.doc?._source) {
                            return doc.doc._source;
                        } else if (doc?.doc) {
                            return doc.doc;
                        } else if (doc?._source) {
                            return doc._source;
                        } else {
                            return doc;
                        }
                    })
                    .filter(doc => doc != null); // Filter out any null/undefined documents
            }
            
            // Create the verified card with expandable documents section
            const card = document.createElement('div');
            card.id = 'step-verified';
            card.className = 'bg-gray-900/50 rounded-lg border border-green-500/40';
            
            card.innerHTML = `
                <button class="w-full p-4 flex items-center justify-between text-left hover:bg-gray-800/50 transition-colors" onclick="toggleSection('verifiedDocumentsSection')">
                    <div class="flex items-start gap-3">
                        <svg class="w-6 h-6 text-green-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div class="flex-1">
                            <h4 class="text-white font-semibold mb-1">✓ Pipeline Generated and Verified</h4>
                            <p class="text-sm text-gray-400">${data.verification.message}</p>
                            <p class="text-xs text-gray-500 mt-1">Confidence: ${(data.verification.confidence * 100).toFixed(0)}% | Attempts: ${attempts}</p>
                        </div>
                    </div>
                    <svg id="verifiedDocumentsChevron" class="w-5 h-5 text-gray-400 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                </button>
                <div id="verifiedDocumentsSection" class="hidden border-t border-gray-700 p-4">
                    <div class="mb-3">
                        <strong class="text-blue-300">Parsed Documents (${parsedDocuments.length}):</strong>
                    </div>
                    <div class="space-y-3 max-h-96 overflow-y-auto">
                        ${parsedDocuments.map((doc, index) => `
                            <div class="bg-gray-800 rounded-lg p-3">
                                <div class="text-xs text-gray-400 mb-2">Document ${index + 1}</div>
                                <pre class="text-sm overflow-x-auto"><code class="language-json">${JSON.stringify(doc, null, 2)}</code></pre>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
            container.appendChild(card);
            
            // Add loading indicator for next step
            addLoadingCard(container, 'pipeline-loading', 'Creating ingest pipeline...');
        }
        else if (data.step === 'generating') {
            // Remove initial loading card
            removeLoadingCard(container, 'initial-loading');
            // Remove any previous generating card
            removeLoadingCard(container, 'generating-loading');
            
            // Show simple generation message
            addLoadingCard(container, 'generating-loading', 'Generating Pipeline');
        }
        else if (data.step === 'verifying') {
            // Remove generating card
            removeLoadingCard(container, 'generating-loading');
            
            // Show simple verification message
            addLoadingCard(container, 'verifying-loading', 'Verifying Pipeline');
        }
        else if (data.step === 'attempt_failed') {
            // Remove loading cards
            removeLoadingCard(container, 'generating-loading');
            removeLoadingCard(container, 'verifying-loading');
            
            // Build content with error and formatted pipeline JSON
            const errorMessage = escapeHtml(data.error || 'Unknown error occurred');
            const pipelineJson = JSON.stringify(data.pipeline, null, 2);
            const content = `<div class="mb-4">${errorMessage}</div><div class="mt-4"><strong class="text-blue-300">Generated Pipeline:</strong><pre class="mt-2 bg-gray-800 p-3 rounded overflow-x-auto"><code>${escapeHtml(pipelineJson)}</code></pre></div>`;
            
            // Add expandable card for failed attempt with blue retry icon
            addCollapsibleCard(container, `failed-${data.attempt}`, {
                title: '<svg class="w-5 h-5 inline-block text-blue-400 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>Retrying pipeline generation',
                subtitle: `Generation Attempt ${data.attempt}/${data.max_attempts || 5}`,
                content: content,
                isHtml: true
            });
        }
        else if (data.step === 'verification_failed') {
            // Remove loading cards
            removeLoadingCard(container, 'generating-loading');
            removeLoadingCard(container, 'verifying-loading');
            
            // Build content with error and formatted pipeline JSON
            const errorMessage = escapeHtml(data.error || 'Verification failed, trying again...');
            const pipelineJson = JSON.stringify(data.pipeline, null, 2);
            const content = `<div class="mb-4">${errorMessage}</div><div class="mt-4"><strong class="text-blue-300">Generated Pipeline:</strong><pre class="mt-2 bg-gray-800 p-3 rounded overflow-x-auto"><code>${escapeHtml(pipelineJson)}</code></pre></div>`;
            
            // Add expandable card for failed verification with blue retry icon
            addCollapsibleCard(container, `verification-failed-${data.attempt}`, {
                title: '<svg class="w-5 h-5 inline-block text-blue-400 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" /></svg>Retrying pipeline generation',
                subtitle: `Generation Attempt ${data.attempt}/${data.max_attempts || 5}`,
                content: content,
                isHtml: true
            });
        }
        else if (data.step === 'pipeline_created') {
            // Remove the "Creating ingest pipeline..." loading card
            removeLoadingCard(container, 'pipeline-loading');
            
            addCollapsibleCard(container, 'pipeline', {
                title: '✓ Ingest Pipeline Created',
                subtitle: `Pipeline: ${data.pipeline_name}`,
                content: data.pipeline
            });
            // Add loading indicator for next step
            addLoadingCard(container, 'template-loading', 'Creating index template...');
        }
        else if (data.step === 'template_created') {
            // Remove loading indicator
            removeLoadingCard(container, 'template-loading');
            
            addCollapsibleCard(container, 'template', {
                title: '✓ Index Template Created',
                subtitle: `Template: ${data.template_name}`,
                content: data.template
            });
            // Add loading indicator for next step
            addLoadingCard(container, 'ingest-loading', 'Ingesting data...');
        }
        else if (data.step === 'data_ingested') {
            // Remove loading indicator
            removeLoadingCard(container, 'ingest-loading');
            
            addStepCard(container, 'ingested', {
                title: '✓ Data Ingested',
                message: `Data Stream: ${data.data_stream_name || 'N/A'}`,
                detail: `${data.docs_ingested || 0} documents ingested successfully`
            });
            // Add loading indicator for next step
            addLoadingCard(container, 'dashboard-loading', 'Creating Kibana dashboard...');
        }
        else if (data.step === 'dashboard_created') {
            // Remove loading indicator
            removeLoadingCard(container, 'dashboard-loading');
            
            // Pause the timer - integration is complete
            if (!timerPaused) {
                pauseTimer();
            }
            
            addDashboardCard(container, {
                dashboard_id: data.dashboard_id,
                dashboard_url: data.dashboard_url,
                dashboard_json: data.dashboard_json
            });
        }
        else if (data.step === 'complete') {
            addCompleteCard(container, data.assets || {});
        }
        else if (data.step === 'error') {
            // Remove any loading indicators including initial
            removeLoadingCard(container, 'initial-loading');
            const loadingCards = container.querySelectorAll('[id$="-loading"]');
            loadingCards.forEach(card => card.remove());
            
            // Show error message
            container.innerHTML += `<div class="alert alert-error"><span>${data.message}</span></div>`;
            
            // If any assets were created before the error, show delete button
            if (data.assets) {
                const hasAssets = Object.values(data.assets).some(asset => asset !== null);
                if (hasAssets) {
                    addErrorCleanupCard(container, data.assets);
                }
            }
        }
        else {
            // For any other step, make sure initial loading is removed
            removeLoadingCard(container, 'initial-loading');
        }
    }

    function addLoadingCard(container, id, message) {
        const card = document.createElement('div');
        card.id = id;
        card.className = 'bg-gray-900/50 rounded-lg p-4 border border-gray-600';
        card.innerHTML = `
            <div class="flex items-start gap-3">
                <span class="loading loading-spinner loading-md text-purple-400"></span>
                <div class="flex-1">
                    <p class="text-gray-400">${message}</p>
                </div>
            </div>
        `;
        container.appendChild(card);
    }

    function removeLoadingCard(container, id) {
        const card = document.getElementById(id);
        if (card) {
            card.remove();
        }
    }

    function addStepCard(container, id, { title, message, detail }) {
        const card = document.createElement('div');
        card.id = `step-${id}`;
        card.className = 'bg-gray-900/50 rounded-lg p-4 border border-green-500/40';
        card.innerHTML = `
            <div class="flex items-start gap-3">
                <svg class="w-6 h-6 text-green-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div class="flex-1">
                    <h4 class="text-white font-semibold mb-1">${title}</h4>
                    <p class="text-sm text-gray-400">${message}</p>
                    ${detail ? `<p class="text-xs text-gray-500 mt-1">${detail}</p>` : ''}
                </div>
            </div>
        `;
        container.appendChild(card);
    }

    function addCollapsibleCard(container, id, { title, subtitle, content, isHtml = false }) {
        const card = document.createElement('div');
        card.id = `step-${id}`;
        card.className = 'bg-gray-900/50 rounded-lg border border-green-500/40';
        
        // Determine content display based on whether it's HTML or JSON
        const contentDisplay = isHtml 
            ? content 
            : `<pre class="bg-gray-800 p-4 rounded-lg overflow-x-auto text-sm"><code class="language-json">${JSON.stringify(content, null, 2)}</code></pre>`;
        
        card.innerHTML = `
            <button class="w-full p-4 flex items-center justify-between text-left hover:bg-gray-800/50 transition-colors" onclick="toggleSection('${id}Section')">
                <div class="flex items-start gap-3">
                    <svg class="w-6 h-6 text-green-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div class="flex-1">
                        <h4 class="text-white font-semibold mb-1">${title}</h4>
                        <p class="text-sm text-gray-400">${subtitle.replace(/logs-\w+-\w+/, '<code class="text-purple-400">$&</code>')}</p>
                    </div>
                </div>
                <svg id="${id}Chevron" class="w-5 h-5 text-gray-400 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                </svg>
            </button>
            <div id="${id}Section" class="hidden border-t border-gray-700 p-4 max-h-96 overflow-y-auto">
                ${contentDisplay}
            </div>
        `;
        container.appendChild(card);
    }

    function addDashboardCard(container, { dashboard_id, dashboard_url, dashboard_json }) {
        // Create a single expandable card with dashboard info and JSON
        const card = document.createElement('div');
        card.id = 'step-dashboard';
        card.className = 'bg-gray-900/50 rounded-lg border border-green-500/40';
        
        card.innerHTML = `
            <div class="p-4">
                <div class="flex items-start gap-3 mb-3">
                    <svg class="w-6 h-6 text-green-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div class="flex-1">
                        <h4 class="text-white font-semibold mb-1">✓ Kibana Dashboard Created</h4>
                        <p class="text-sm text-gray-400 mb-3">Dashboard ID: <code class="text-purple-400">${dashboard_id}</code></p>
                        <a href="${dashboard_url}" target="_blank" class="inline-flex items-center gap-2 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition-colors">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                            Open Dashboard in Kibana
                        </a>
                    </div>
                </div>
                <button class="w-full flex items-center justify-between text-left hover:bg-gray-800/50 transition-colors p-3 rounded-lg" onclick="toggleSection('dashboardSection')">
                    <span class="text-sm text-gray-300">View Dashboard JSON</span>
                    <svg id="dashboardChevron" class="w-5 h-5 text-gray-400 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                    </svg>
                </button>
            </div>
            <div id="dashboardSection" class="hidden border-t border-gray-700 p-4">
                <strong class="text-blue-300">Dashboard JSON:</strong>
                <pre class="mt-2 bg-gray-800 p-4 rounded-lg overflow-x-auto text-sm max-h-96 overflow-y-auto"><code class="language-json">${JSON.stringify(dashboard_json, null, 2)}</code></pre>
            </div>
        `;
        container.appendChild(card);
    }

    function addCompleteCard(container, assets = {}) {
        const card = document.createElement('div');
        card.id = 'step-complete';
        card.className = 'bg-green-900/20 border border-green-500/40 rounded-lg p-4';
        card.innerHTML = `
            <div class="flex items-start gap-3 mb-4">
                <svg class="w-6 h-6 text-green-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                <div class="flex-1">
                    <h4 class="text-green-300 font-semibold mb-1">Integration Complete!</h4>
                    <p class="text-sm text-gray-300 mb-3">Your logs are now being ingested and parsed in Elasticsearch with a ready-to-use Kibana dashboard for visualization.</p>
                    
                    ${Object.keys(assets).length > 0 ? `
                        <div class="bg-gray-800/50 rounded-lg p-3 mb-3">
                            <strong class="text-blue-300 text-sm">Created Assets:</strong>
                            <ul class="text-sm text-gray-300 mt-2 space-y-1">
                                ${assets.pipeline_name ? `<li>• <strong>Ingest Pipeline:</strong> <code class="text-purple-400">${assets.pipeline_name}</code></li>` : ''}
                                ${assets.template_name ? `<li>• <strong>Index Template:</strong> <code class="text-purple-400">${assets.template_name}</code></li>` : ''}
                                ${assets.data_stream_name ? `<li>• <strong>Data Stream:</strong> <code class="text-purple-400">${assets.data_stream_name}</code></li>` : ''}
                                ${assets.dashboard_id ? `<li>• <strong>Dashboard:</strong> <code class="text-purple-400">${assets.dashboard_id}</code></li>` : ''}
                            </ul>
                        </div>
                        <button id="deleteAssetsBtn" class="btn btn-error w-full">
                            <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                            </svg>
                            Delete Generated Assets
                        </button>
                    ` : ''}
                </div>
            </div>
        `;
        container.appendChild(card);
        
        // Add delete button event listener
        if (Object.keys(assets).length > 0) {
            setTimeout(() => {
                const deleteBtn = document.getElementById('deleteAssetsBtn');
                if (deleteBtn) {
                    deleteBtn.addEventListener('click', async () => {
                        const confirmed = await ConfirmationModal.show(
                            'Are you sure you want to delete all generated assets? This action cannot be undone.',
                            'Delete Generated Assets',
                            'Delete Assets'
                        );
                        
                        if (!confirmed) return;
                        
                        await deleteAssets(deleteBtn, assets);
                    });
                }
            }, 0);
        }
    }
    
    async function deleteAssets(deleteBtn, assets) {
        if (!deleteBtn) {
            console.error('Delete button not found');
            return;
        }
        
        console.log('Deleting assets:', assets);
        
        deleteBtn.disabled = true;
        deleteBtn.innerHTML = '<span class="loading loading-spinner loading-sm mr-2"></span>Deleting...';
        
        try {
            // Get CSRF token
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]')?.value;
            
            const response = await fetch('/AI/IntegrationFactory/delete/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken || ''
                },
                body: JSON.stringify({
                    connection_id: connectionSelect.value,
                    assets: assets
                })
            });
            
            console.log('Delete response status:', response.status);
            
            const result = await response.json();
            
            if (result.success) {
                deleteBtn.className = 'btn btn-success w-full';
                deleteBtn.innerHTML = `
                    <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
                    </svg>
                    Assets Deleted Successfully
                `;
                deleteBtn.disabled = true;
            } else {
                throw new Error(result.error || 'Failed to delete assets');
            }
        } catch (error) {
            deleteBtn.disabled = false;
            deleteBtn.className = 'btn btn-error w-full';
            deleteBtn.innerHTML = `
                <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
                Delete Generated Assets
            `;
            
            // Show error in custom modal
            await ConfirmationModal.show(
                `Error deleting assets: ${error.message}`,
                'Deletion Error',
                'OK'
            );
        }
    }

    function addErrorCleanupCard(container, assets) {
        const card = document.createElement('div');
        card.id = 'error-cleanup';
        card.className = 'bg-gray-900/50 rounded-lg border border-yellow-500/40 p-4 mt-4';
        
        // Filter out null assets
        const createdAssets = Object.entries(assets).filter(([_, value]) => value !== null);
        
        const assetsList = createdAssets.map(([key, value]) => {
            const label = key.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());
            return `<li class="text-sm"><span class="font-medium text-yellow-400">${label}:</span> <code class="text-purple-400">${value}</code></li>`;
        }).join('');
        
        card.innerHTML = `
            <div class="flex items-start gap-3 mb-3">
                <svg class="w-6 h-6 text-yellow-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <div class="flex-1">
                    <h4 class="text-white font-semibold mb-1">⚠ Partial Assets Created</h4>
                    <p class="text-sm text-gray-400 mb-3">The following assets were created before the error occurred:</p>
                    <ul class="space-y-1 mb-4">${assetsList}</ul>
                    <button id="cleanup-delete-btn" class="btn btn-warning w-full">
                        <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                        </svg>
                        Clean Up Partial Assets
                    </button>
                </div>
            </div>
        `;
        
        container.appendChild(card);
        
        // Add delete handler
        const deleteBtn = document.getElementById('cleanup-delete-btn');
        deleteBtn.addEventListener('click', async () => {
            const confirmed = await ConfirmationModal.show(
                'This will delete all partially created assets. This action cannot be undone.',
                'Clean Up Partial Assets?',
                'Delete Assets'
            );
            
            if (!confirmed) return;
            
            await deleteAssets(deleteBtn, assets);
        });
    }

    async function installPrebuiltIntegration() {
        const connectionId = connectionSelect.value;
        const integrationName = classificationData.integration_name;
        
        // Get log samples from form
        const formData = new FormData(form);
        let logSamples = [];
        
        if (logInput.value.trim()) {
            // Parse pasted logs
            const lines = logInput.value.trim().split('\n').filter(line => line.trim());
            logSamples = lines.map(line => ({ message: line, event: { original: line } }));
        } else if (logFile.files.length > 0) {
            // File upload - we'll need to read it
            const file = logFile.files[0];
            const text = await file.text();
            const lines = text.trim().split('\n').filter(line => line.trim());
            logSamples = lines.map(line => ({ message: line, event: { original: line } }));
        }
        
        // Show loading in pipeline area
        pipelineArea.classList.remove('hidden');
        pipelineOutput.innerHTML = '<div class="text-center py-8"><span class="loading loading-spinner loading-lg"></span><p class="mt-4 text-gray-400">Installing prebuilt integration...</p></div>';
        
        try {
            const response = await fetch('/AI/IntegrationFactory/install-prebuilt/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    connection_id: connectionId,
                    integration_name: integrationName,
                    log_samples: logSamples
                })
            });
            
            if (!response.ok) {
                throw new Error('Failed to install integration');
            }
            
            const result = await response.json();
            displayPrebuiltIntegrationResults(result);
            
            // Stop the timer on success
            stopTimer();
            
        } catch (error) {
            pipelineOutput.innerHTML = `<div class="alert alert-error"><span>Error: ${error.message}</span></div>`;
        }
    }
    
    function displayPrebuiltIntegrationResults(result) {
        const { integration_name, version, dashboards, assets, total_assets, ingested_docs, data_stream, ingestion_errors } = result;
        
        let html = `
            <div class="bg-gray-900/50 rounded-lg p-6 border border-green-500/40">
                <div class="flex items-start gap-3 mb-4">
                    <svg class="w-6 h-6 text-green-400 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    <div class="flex-1">
                        <h3 class="text-white font-semibold text-lg mb-2">✅ Integration Installed Successfully!</h3>
                        <p class="text-gray-400 mb-4">Installed <strong class="text-purple-400">${integration_name}</strong> version <strong class="text-purple-400">${version}</strong></p>
                        <div class="text-sm text-gray-400 space-y-1">
                            <p>Total assets imported: <strong class="text-white">${total_assets}</strong></p>
                            ${data_stream ? `
                                <p>Sample documents ingested: <strong class="text-white">${ingested_docs || 0}</strong></p>
                                <p>Data stream: <code class="text-purple-400">${data_stream}</code></p>
                            ` : ''}
                        </div>
                        ${ingestion_errors && ingestion_errors.length > 0 ? `
                            <div class="mt-3 p-3 bg-yellow-900/20 border border-yellow-500/40 rounded">
                                <p class="text-yellow-400 font-semibold mb-2">⚠️ Ingestion Warnings:</p>
                                <ul class="text-sm text-yellow-300 space-y-1 max-h-32 overflow-y-auto">
                                    ${ingestion_errors.map(err => `<li class="break-words">• ${err.message}</li>`).join('')}
                                </ul>
                                <p class="text-xs text-yellow-400 mt-2">Note: OOTB integrations expect specific log formats. Your sample logs may not match the expected format.</p>
                            </div>
                        ` : ''}
                    </div>
                </div>
        `;
        
        // Show dashboards with links
        if (dashboards && dashboards.length > 0) {
            html += `
                <div class="mt-6 pt-6 border-t border-gray-700">
                    <h4 class="text-white font-semibold mb-3 flex items-center gap-2">
                        <svg class="w-5 h-5 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
                        </svg>
                        Dashboards (${dashboards.length})
                    </h4>
                    <div class="space-y-2">
            `;
            
            dashboards.forEach(dashboard => {
                html += `
                    <a href="${dashboard.url}" target="_blank" class="block p-3 bg-gray-800/50 rounded border border-gray-700 hover:border-blue-500 hover:bg-gray-800 transition-colors">
                        <div class="flex items-center justify-between">
                            <code class="text-sm text-purple-400">${dashboard.id}</code>
                            <svg class="w-4 h-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                            </svg>
                        </div>
                    </a>
                `;
            });
            
            html += `
                    </div>
                </div>
            `;
        }
        
        // Show other assets summary
        if (assets && assets.length > 0) {
            const assetsByType = {};
            assets.forEach(asset => {
                const type = asset.type || 'other';
                if (!assetsByType[type]) {
                    assetsByType[type] = [];
                }
                assetsByType[type].push(asset.id);
            });
            
            html += `
                <div class="mt-6 pt-6 border-t border-gray-700">
                    <h4 class="text-white font-semibold mb-3">Other Assets</h4>
                    <div class="grid grid-cols-2 gap-3">
            `;
            
            for (const [type, ids] of Object.entries(assetsByType)) {
                const displayType = type.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                html += `
                    <div class="p-3 bg-gray-800/30 rounded border border-gray-700">
                        <div class="text-sm font-medium text-gray-400 mb-1">${displayType}</div>
                        <div class="text-lg font-semibold text-white">${ids.length}</div>
                    </div>
                `;
            }
            
            html += `
                    </div>
                </div>
            `;
        }
        
        html += `
            </div>
        `;
        
        pipelineOutput.innerHTML = html;
    }

    // Toggle section visibility
    window.toggleSection = function(sectionId) {
        const section = document.getElementById(sectionId);
        const chevronId = sectionId.replace('Section', 'Chevron');
        const chevron = document.getElementById(chevronId);
        
        if (section.classList.contains('hidden')) {
            section.classList.remove('hidden');
            chevron.style.transform = 'rotate(180deg)';
        } else {
            section.classList.add('hidden');
            chevron.style.transform = 'rotate(0deg)';
        }
    }

    elasticsearchPipelineBtn.addEventListener('click', () => generatePipeline('elasticsearch'));
    logstashPipelineBtn.addEventListener('click', () => {
        // Do nothing for Logstash Pipeline button for now
        console.log('Logstash Pipeline clicked - functionality not implemented yet');
        return;
    });

});
