/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

/**
 * Recursively count all plugins in the pipeline, including nested plugins in conditionals
 * @param {Object} components - The components object with input, filter, output arrays
 * @returns {number} - Total count of plugins (excluding comments and conditionals themselves)
 */
function countTotalPlugins(components) {
    let totalCount = 0;
    
    /**
     * Recursively count plugins in a component, including nested conditionals
     * @param {Object} component - A single component to count
     */
    function countComponentPlugins(component) {
        // Skip comment plugins - they're not real plugins
        if (component.plugin === 'comment') {
            return;
        }
        
        // If it's a conditional (if), don't count it but count its nested plugins
        if (component.plugin === 'if') {
            // Count plugins in the main if block
            if (component.config && component.config.plugins && Array.isArray(component.config.plugins)) {
                component.config.plugins.forEach(nestedPlugin => {
                    countComponentPlugins(nestedPlugin);
                });
            }
            
            // Count plugins in else-if blocks
            if (component.config && component.config.else_ifs && Array.isArray(component.config.else_ifs)) {
                component.config.else_ifs.forEach(elseIf => {
                    if (elseIf.plugins && Array.isArray(elseIf.plugins)) {
                        elseIf.plugins.forEach(nestedPlugin => {
                            countComponentPlugins(nestedPlugin);
                        });
                    }
                });
            }
            
            // Count plugins in else block
            if (component.config && component.config.else && component.config.else.plugins && Array.isArray(component.config.else.plugins)) {
                component.config.else.plugins.forEach(nestedPlugin => {
                    countComponentPlugins(nestedPlugin);
                });
            }
        } else {
            // It's a regular plugin, count it
            totalCount++;
        }
    }
    
    // Count plugins in each section (input, filter, output)
    ['input', 'filter', 'output'].forEach(type => {
        if (components[type] && Array.isArray(components[type])) {
            components[type].forEach(component => {
                countComponentPlugins(component);
            });
        }
    });
    
    return totalCount;
}

/**
 * Recursively count all conditional blocks (if, else-if, else) in the pipeline
 * @param {Object} components - The components object with input, filter, output arrays
 * @returns {number} - Total count of conditional blocks
 */
function countTotalConditions(components) {
    let totalCount = 0;
    
    /**
     * Recursively count conditional blocks in a component
     * @param {Object} component - A single component to check
     */
    function countComponentConditions(component) {
        // If it's a conditional (if), count it and its branches
        if (component.plugin === 'if') {
            // Count the main if block
            totalCount++;
            
            // Count else-if blocks
            if (component.config && component.config.else_ifs && Array.isArray(component.config.else_ifs)) {
                totalCount += component.config.else_ifs.length;
                
                // Check for nested conditionals in else-if blocks
                component.config.else_ifs.forEach(elseIf => {
                    if (elseIf.plugins && Array.isArray(elseIf.plugins)) {
                        elseIf.plugins.forEach(nestedPlugin => {
                            countComponentConditions(nestedPlugin);
                        });
                    }
                });
            }
            
            // Count else block if it exists
            if (component.config && component.config.else) {
                totalCount++;
                
                // Check for nested conditionals in else block
                if (component.config.else.plugins && Array.isArray(component.config.else.plugins)) {
                    component.config.else.plugins.forEach(nestedPlugin => {
                        countComponentConditions(nestedPlugin);
                    });
                }
            }
            
            // Check for nested conditionals in main if block
            if (component.config && component.config.plugins && Array.isArray(component.config.plugins)) {
                component.config.plugins.forEach(nestedPlugin => {
                    countComponentConditions(nestedPlugin);
                });
            }
        }
    }
    
    // Count conditions in each section (input, filter, output)
    ['input', 'filter', 'output'].forEach(type => {
        if (components[type] && Array.isArray(components[type])) {
            components[type].forEach(component => {
                countComponentConditions(component);
            });
        }
    });
    
    return totalCount;
}

/**
 * Count password-type fields across all plugins that have plaintext (non-keystore) values
 * @param {Object} components - The components object with input, filter, output arrays
 * @returns {number} - Count of plaintext password fields
 */
function countPlaintextPasswords(components) {
    const pluginDataSource = window.pluginData;
    if (!pluginDataSource) return 0;
    let count = 0;

    function checkComponent(component) {
        if (component.plugin === 'comment') return;
        if (component.plugin === 'if') {
            (component.config?.plugins || []).forEach(checkComponent);
            (component.config?.else_ifs || []).forEach(ei => (ei.plugins || []).forEach(checkComponent));
            (component.config?.else?.plugins || []).forEach(checkComponent);
        } else {
            const pluginInfo = pluginDataSource[component.type]?.[component.plugin];
            if (!pluginInfo?.options) return;
            Object.entries(pluginInfo.options).forEach(([key, option]) => {
                // Check if this is a sensitive field type (password, api_key, secret, token, etc.)
                const inputType = (option.input_type || '').toLowerCase();
                const isSensitiveType = inputType === 'password' || 
                                       inputType === 'api_key' || 
                                       inputType === 'apikey' ||
                                       inputType === 'token' ||
                                       inputType === 'secret';
                if (isSensitiveType) {
                    const val = component.config?.[key];
                    if (val && !String(val).startsWith('${')) {
                        count++;
                    }
                }
            });
        }
    }

    ['input', 'filter', 'output'].forEach(type => {
        (components[type] || []).forEach(checkComponent);
    });
    return count;
}

/**
 * Update the stats strip with current pipeline statistics
 */
function updateStatsStrip() {
    // Only update if components is defined
    if (typeof components === 'undefined') {
        return;
    }
    
    // Count total plugins
    const totalPlugins = countTotalPlugins(components);
    
    // Count total conditions
    const totalConditions = countTotalConditions(components);
    
    // Update the display
    const totalPluginsElement = document.getElementById('totalPluginsCount');
    if (totalPluginsElement) {
        totalPluginsElement.textContent = totalPlugins;
    }
    
    const totalConditionsElement = document.getElementById('totalConditionsCount');
    if (totalConditionsElement) {
        totalConditionsElement.textContent = totalConditions;
    }

    // Count plaintext passwords
    const plaintextPasswords = countPlaintextPasswords(components);
    const plaintextEl = document.getElementById('plaintextPasswordsCount');
    if (plaintextEl) plaintextEl.textContent = plaintextPasswords;
    const plaintextIndicator = document.getElementById('plaintextPasswordsIndicator');
    if (plaintextIndicator) {
        // Always show the indicator, even when count is 0
        plaintextIndicator.classList.remove('hidden');
    }
}

// Make updateStatsStrip globally available
window.updateStatsStrip = updateStatsStrip;
