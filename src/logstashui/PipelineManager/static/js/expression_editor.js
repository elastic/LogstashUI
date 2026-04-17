/*
 * Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
 * or more contributor license agreements. Licensed under the Elastic License;
 * you may not use this file except in compliance with the Elastic License.
 */

// Expression Editor State
let currentExpression = '';
let currentComponentId = null;
let currentFieldName = null;
let currentElseIfIndex = null;

/**
 * Open the expression editor modal
 * @param {string} componentId - The ID of the component being edited
 * @param {string} fieldName - The name of the field being edited (optional)
 * @param {string} initialValue - Initial expression value (optional)
 * @param {number} elseIfIndex - Index of else-if block being edited (optional)
 */
function openExpressionEditor(componentId, fieldName = null, initialValue = '', elseIfIndex = null) {
    currentComponentId = componentId;
    currentFieldName = fieldName;
    currentExpression = initialValue;
    currentElseIfIndex = elseIfIndex;
    
    // Update the display
    updateExpressionDisplay();
    
    // Clear input fields
    document.getElementById('leftOperand').value = '';
    document.getElementById('rightOperand').value = '';
    
    // Show the modal
    const modal = document.getElementById('expressionEditorModal');
    if (modal) {
        modal.classList.remove('hidden');
    }
}

/**
 * Close the expression editor modal
 */
function closeExpressionEditor() {
    const modal = document.getElementById('expressionEditorModal');
    if (modal) {
        modal.classList.add('hidden');
    }
    
    // Reset state
    currentExpression = '';
    currentComponentId = null;
    currentFieldName = null;
    currentElseIfIndex = null;
    
    // Clear input fields
    document.getElementById('leftOperand').value = '';
    document.getElementById('rightOperand').value = '';
}

/**
 * Update the expression display
 */
function updateExpressionDisplay() {
    const display = document.getElementById('expressionDisplay');
    if (!display) return;
    
    if (currentExpression.trim() === '') {
        display.innerHTML = '<span class="text-gray-500">Build your expression below...</span>';
    } else {
        display.innerHTML = `<span class="text-green-400">${escapeHtml(currentExpression)}</span>`;
    }
}

/**
 * Add a comparison/regex/containment operator to the expression
 * @param {string} operator - The operator to add
 */
function addOperator(operator) {
    const leftOperand = document.getElementById('leftOperand').value.trim();
    const rightOperand = document.getElementById('rightOperand').value.trim();
    
    if (!leftOperand || !rightOperand) {
        alert('Please enter both left and right operands before adding an operator.');
        return;
    }
    
    // Build the expression part
    let expressionPart = `${leftOperand} ${operator} ${rightOperand}`;
    
    // Add to current expression
    if (currentExpression.trim() === '') {
        currentExpression = expressionPart;
    } else {
        // If there's already an expression, we need to decide how to combine
        // For now, just append (user can add boolean operators separately)
        currentExpression += ` ${expressionPart}`;
    }
    
    // Update display
    updateExpressionDisplay();
    
    // Clear operand fields
    document.getElementById('leftOperand').value = '';
    document.getElementById('rightOperand').value = '';
}

/**
 * Add a boolean operator (and, or, nand, xor) to combine expressions
 * @param {string} operator - The boolean operator to add
 */
function addBooleanOperator(operator) {
    if (currentExpression.trim() === '') {
        alert('Please build an expression first before adding a boolean operator.');
        return;
    }
    
    // Add the boolean operator at the end
    currentExpression += ` ${operator} `;
    
    // Update display
    updateExpressionDisplay();
}

/**
 * Add a unary operator (!) to the expression
 * @param {string} operator - The unary operator to add
 */
function addUnaryOperator(operator) {
    const leftOperand = document.getElementById('leftOperand').value.trim();
    
    if (!leftOperand) {
        alert('Please enter a left operand for the NOT operator.');
        return;
    }
    
    // Build the expression part
    let expressionPart = `${operator}${leftOperand}`;
    
    // Add to current expression
    if (currentExpression.trim() === '') {
        currentExpression = expressionPart;
    } else {
        currentExpression += ` ${expressionPart}`;
    }
    
    // Update display
    updateExpressionDisplay();
    
    // Clear operand field
    document.getElementById('leftOperand').value = '';
}

/**
 * Add parentheses around the current expression
 */
function addParentheses() {
    if (currentExpression.trim() === '') {
        // Add empty parentheses for user to fill
        currentExpression = '()';
    } else {
        // Wrap current expression in parentheses
        currentExpression = `(${currentExpression})`;
    }
    
    // Update display
    updateExpressionDisplay();
}

/**
 * Clear the current expression
 */
function clearExpression() {
    currentExpression = '';
    updateExpressionDisplay();
    
    // Clear input fields
    document.getElementById('leftOperand').value = '';
    document.getElementById('rightOperand').value = '';
}

/**
 * Apply the expression to the component
 */
function applyExpression() {
    if (currentExpression.trim() === '') {
        alert('Please build an expression before applying.');
        return;
    }
    
    if (!currentComponentId) {
        alert('No component selected.');
        return;
    }
    
    // Find the component in the components data structure
    const component = findComponentById(currentComponentId);
    
    if (!component) {
        alert('Component not found.');
        return;
    }
    
    // If a specific field was provided, update that field
    // Otherwise, update the 'condition' field (for if statements) or a default field
    if (currentFieldName) {
        component.config[currentFieldName] = currentExpression;
    } else if (component.plugin === 'if') {
        // Check if this is for an else-if block
        if (currentElseIfIndex !== null && component.config.else_ifs && component.config.else_ifs[currentElseIfIndex]) {
            // Update the else-if condition
            component.config.else_ifs[currentElseIfIndex].condition = currentExpression;
        } else {
            // For main if conditional block, update the condition
            component.config.condition = currentExpression;
        }
    } else {
        // For other plugins, we might want to update a specific field
        // This could be customized based on the plugin type
        // For now, let's assume there's a generic 'expression' or 'condition' field
        if (!component.config.condition && !component.config.expression) {
            // Ask user which field to update
            const fieldName = prompt('Enter the field name to store this expression:', 'condition');
            if (fieldName) {
                component.config[fieldName] = currentExpression;
            } else {
                return;
            }
        } else {
            component.config.condition = currentExpression;
        }
    }
    
    // Reload the UI to reflect changes
    loadExistingComponents();
    
    // Close the modal
    closeExpressionEditor();
    
    // Show success message
    console.log('Expression applied:', currentExpression);
}


// Event listener setup when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    // Add event listeners to expression editor buttons in the component rows
    document.addEventListener('click', function(event) {
        const expressionBtn = event.target.closest('.expression-editor-btn');
        if (expressionBtn) {
            event.stopPropagation();
            const componentId = expressionBtn.getAttribute('data-component-id');
            const elseIfIndexAttr = expressionBtn.getAttribute('data-elseif-index');
            const elseIfIndex = elseIfIndexAttr !== null ? parseInt(elseIfIndexAttr) : null;
            
            // Find the component to get its current expression/condition
            const component = findComponentById(componentId);
            let initialValue = '';
            
            if (component) {
                // Check if this is for an else-if block
                if (elseIfIndex !== null && component.config.else_ifs && component.config.else_ifs[elseIfIndex]) {
                    initialValue = component.config.else_ifs[elseIfIndex].condition || '';
                } else {
                    // Try to find an existing expression or condition for main if block
                    initialValue = component.config.condition || component.config.expression || '';
                }
            }
            
            openExpressionEditor(componentId, null, initialValue, elseIfIndex);
        }
    });
    
    // Allow Enter key in operand fields to trigger operator addition
    const leftOperand = document.getElementById('leftOperand');
    const rightOperand = document.getElementById('rightOperand');
    
    if (leftOperand && rightOperand) {
        const handleEnter = (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                // Focus on the right operand if left is filled
                if (e.target === leftOperand && leftOperand.value.trim()) {
                    rightOperand.focus();
                }
            }
        };
        
        leftOperand.addEventListener('keypress', handleEnter);
        rightOperand.addEventListener('keypress', handleEnter);
    }
});
