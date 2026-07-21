#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import StreamingHttpResponse, JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from Common.elastic_utils import (
    stream_chat_completion, get_inference_models, simulate_ingest_pipeline,
    create_ingest_pipeline, create_index_template, ingest_to_data_stream,
    create_kibana_dashboard, delete_ingest_pipeline, delete_index_template,
    delete_data_stream, delete_kibana_dashboard, install_fleet_integration,
    get_kibana_url
)
import os
import logging
import json
logger = logging.getLogger(__name__)


def load_system_prompt(filename):
    """Load a system prompt from the system_prompts directory"""
    prompt_path = os.path.join(os.path.dirname(__file__), 'system_prompts', filename)
    logger.info(f"Loading system prompt from: {prompt_path}")
    
    try:
        # Check if file exists
        if not os.path.exists(prompt_path):
            logger.error(f"System prompt file does not exist: {prompt_path}")
            return f"You are an AI assistant helping with {filename.replace('.md', '')}."
        
        # Read the file
        with open(prompt_path, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
            content = f.read()
            
        logger.info(f"Loaded system prompt, length: {len(content)} characters")
        
        if not content or not content.strip():
            logger.error(f"System prompt file is empty: {filename}")
            return f"You are an AI assistant helping with {filename.replace('.md', '')}."
            
        return content
        
    except Exception as e:
        logger.error(f"Error loading system prompt {filename}: {e}", exc_info=True)
        return f"You are an AI assistant helping with {filename.replace('.md', '')}."


def clean_pipeline_json(pipeline):
    """
    Clean up common issues in LLM-generated pipeline JSON
    
    - Remove empty on_failure arrays
    - Ensure proper field types
    """
    if not isinstance(pipeline, dict):
        return pipeline
    
    # Clean processors
    if 'processors' in pipeline and isinstance(pipeline['processors'], list):
        for processor in pipeline['processors']:
            if isinstance(processor, dict):
                for proc_type, proc_config in processor.items():
                    if isinstance(proc_config, dict):
                        # Remove empty on_failure arrays
                        if 'on_failure' in proc_config:
                            if not proc_config['on_failure'] or proc_config['on_failure'] == []:
                                del proc_config['on_failure']
                            # Recursively clean nested on_failure processors
                            elif isinstance(proc_config['on_failure'], list):
                                proc_config['on_failure'] = [
                                    p for p in proc_config['on_failure'] 
                                    if p and isinstance(p, dict) and any(p.values())
                                ]
                                if not proc_config['on_failure']:
                                    del proc_config['on_failure']
    
    return pipeline


def generate_pipeline_json(connection_id, inference_id, system_prompt, classification, log_samples, feedback=""):
    """
    Generate ingest pipeline JSON from LLM
    
    Returns:
        Dict containing pipeline definition or error
    """
    import re
    import os
    
    # Load processor definitions
    processors_file = os.path.join(
        os.path.dirname(__file__),
        'system_prompts',
        'ingest_pipeline_processors.json'
    )
    
    with open(processors_file, 'r') as f:
        processors_data = json.load(f)
    
    # Create a summary of available processors
    processor_summary = {}
    for name, details in processors_data.items():
        processor_summary[name] = {
            'description': details['description'],
            'required_params': [
                param for param, info in details['parameters'].items()
                if info.get('required') == 'yes' or info.get('required') == 'yes*'
            ]
        }
    
    # Load grok patterns
    grok_patterns_file = os.path.join(
        os.path.dirname(__file__),
        'system_prompts',
        'grok_patterns.txt'
    )
    
    with open(grok_patterns_file, 'r', encoding='utf-8') as f:
        grok_patterns = f.read()
    
    user_message = f"""Classification Result:
{json.dumps(classification, indent=2)}

Log Samples:
{log_samples[:2000]}

Available Elasticsearch Ingest Processors:
{json.dumps(processor_summary, indent=2)}

Valid Grok Patterns (use ONLY these patterns):
{grok_patterns}

{feedback}

Generate ONLY the ingest pipeline JSON using the processors and patterns listed above. No markdown, no explanations."""
    
    # Collect full response from LLM
    full_response = ""
    for chunk in stream_chat_completion(connection_id, inference_id, system_prompt, user_message):
        if 'error' in chunk:
            return {'error': chunk['error']}
        
        if 'choices' in chunk:
            for choice in chunk.get('choices', []):
                if 'delta' in choice and 'content' in choice['delta']:
                    full_response += choice['delta']['content']
                elif 'message' in choice and 'content' in choice['message']:
                    full_response += choice['message']['content']
    
    logger.info(f"Pipeline generator response (first 500 chars): {full_response[:500]}")
    
    # Extract JSON from response
    try:
        # Method 1: Try to find complete JSON object by counting braces
        start_idx = full_response.find('{')
        if start_idx != -1:
            brace_count = 0
            for i, char in enumerate(full_response[start_idx:], start=start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = full_response[start_idx:i+1]
                        try:
                            pipeline = json.loads(json_str)
                            if 'processors' in pipeline:
                                return pipeline
                        except:
                            pass
                        break
        
        # Method 2: Extract from code blocks
        if '```json' in full_response:
            json_start = full_response.find('```json') + 7
            json_end = full_response.find('```', json_start)
            json_str = full_response[json_start:json_end].strip()
        elif '```' in full_response:
            json_start = full_response.find('```') + 3
            json_end = full_response.find('```', json_start)
            json_str = full_response[json_start:json_end].strip()
        else:
            json_str = full_response.strip()
        
        pipeline = json.loads(json_str)
        # Clean up common issues
        pipeline = clean_pipeline_json(pipeline)
        return pipeline
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse pipeline JSON: {e}")
        logger.error(f"Response was: {full_response}")
        return {'error': 'Failed to parse pipeline JSON', 'raw_response': full_response}


def generate_index_template_json(connection_id, inference_id, system_prompt, log_samples, pipeline, pipeline_name):
    """
    Generate index template JSON from LLM
    
    Returns:
        Dict containing index template definition or error
    """
    import re
    
    user_message = f"""Log Samples:
{json.dumps(log_samples[:10], indent=2)}

Ingest Pipeline:
{json.dumps(pipeline, indent=2)}

Pipeline Name: {pipeline_name}

Generate an index template for a data stream that uses this pipeline. Return ONLY the JSON template."""
    
    # Collect full response from LLM
    full_response = ""
    for chunk in stream_chat_completion(connection_id, inference_id, system_prompt, user_message):
        if 'error' in chunk:
            return {'error': chunk['error']}
        
        if 'choices' in chunk:
            for choice in chunk.get('choices', []):
                if 'delta' in choice and 'content' in choice['delta']:
                    full_response += choice['delta']['content']
                elif 'message' in choice and 'content' in choice['message']:
                    full_response += choice['message']['content']
    
    logger.info(f"Template creator response (first 500 chars): {full_response[:500]}")
    
    # Extract JSON from response
    try:
        # Method 1: Try to find complete JSON object by counting braces
        start_idx = full_response.find('{')
        if start_idx != -1:
            brace_count = 0
            for i, char in enumerate(full_response[start_idx:], start=start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = full_response[start_idx:i+1]
                        try:
                            template = json.loads(json_str)
                            if 'template' in template or 'index_patterns' in template:
                                return template
                        except:
                            pass
                        break
        
        # Method 2: Extract from code blocks
        if '```json' in full_response:
            json_start = full_response.find('```json') + 7
            json_end = full_response.find('```', json_start)
            json_str = full_response[json_start:json_end].strip()
        elif '```' in full_response:
            json_start = full_response.find('```') + 3
            json_end = full_response.find('```', json_start)
            json_str = full_response[json_start:json_end].strip()
        else:
            json_str = full_response.strip()
        
        template = json.loads(json_str)
        return template
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse template JSON: {e}")
        logger.error(f"Response was: {full_response}")
        return {'error': 'Failed to parse template JSON', 'raw_response': full_response}


def _extract_field_summary(mappings):
    """Return field names grouped by ES type from a mappings dict."""
    result = {
        'keyword': [], 'date': [], 'long': [], 'integer': [],
        'float': [], 'double': [], 'ip': [], 'boolean': [], 'text': [],
    }

    def walk(props, prefix=''):
        for fname, finfo in props.items():
            path = f"{prefix}.{fname}" if prefix else fname
            ftype = finfo.get('type', 'object')
            if ftype in result:
                result[ftype].append(path)
            if 'properties' in finfo:
                walk(finfo['properties'], path)

    walk(mappings.get('properties', {}))
    return result


def generate_dashboard_json(connection_id, inference_id, system_prompt, data_stream_name, template_json, feedback=""):
    """
    Generate Kibana dashboard JSON from LLM

    Returns:
        Dict containing dashboard definition or error
    """
    import re

    # Build a compact field-type reference from the template mappings
    mappings = template_json.get('template', {}).get('mappings', {})
    field_summary = _extract_field_summary(mappings)

    field_hints = []
    if field_summary.get('keyword'):
        field_hints.append(f"Keyword (use TO_STRING() in GROUP BY): {', '.join(field_summary['keyword'][:15])}")
    if field_summary.get('date'):
        field_hints.append(f"Date (use BUCKET() for time series): {', '.join(field_summary['date'][:5])}")
    numerics = (field_summary.get('long', []) + field_summary.get('integer', []) +
                field_summary.get('float', []) + field_summary.get('double', []))
    if numerics:
        field_hints.append(f"Numeric (use AVG/SUM/COUNT): {', '.join(numerics[:10])}")
    if field_summary.get('ip'):
        field_hints.append(f"IP: {', '.join(field_summary['ip'][:5])}")

    fields_text = '\n'.join(field_hints) if field_hints else json.dumps(mappings, indent=2)

    user_message = f"""Data Stream: {data_stream_name}

Available fields by type:
{fields_text}

{feedback}
Generate a Kibana dashboard for this data stream. Return ONLY the JSON object."""
    
    # Collect full response from LLM
    full_response = ""
    for chunk in stream_chat_completion(connection_id, inference_id, system_prompt, user_message):
        if 'error' in chunk:
            return {'error': chunk['error']}
        
        if 'choices' in chunk:
            for choice in chunk.get('choices', []):
                if 'delta' in choice and 'content' in choice['delta']:
                    full_response += choice['delta']['content']
                elif 'message' in choice and 'content' in choice['message']:
                    full_response += choice['message']['content']
    
    logger.debug(f"Dashboard generator full response:\n{full_response}")
    
    # Extract JSON from response
    try:
        # Method 1: Try to extract from code blocks first (most reliable)
        if '```json' in full_response:
            json_start = full_response.find('```json') + 7
            json_end = full_response.find('```', json_start)
            json_str = full_response[json_start:json_end].strip()
            logger.info(f"Extracted JSON from code block (length: {len(json_str)})")
            try:
                dashboard = json.loads(json_str)
                # Check for Kibana saved object structure (title in attributes) or simple dashboard
                if 'title' in dashboard or ('attributes' in dashboard and 'title' in dashboard.get('attributes', {})):
                    return dashboard
            except:
                logger.warning("Failed to parse JSON from code block, trying other methods")
        
        # Method 2: Try to find complete JSON object by counting braces
        start_idx = full_response.find('{')
        if start_idx != -1:
            brace_count = 0
            in_string = False
            escape_next = False
            
            for i, char in enumerate(full_response[start_idx:], start=start_idx):
                if escape_next:
                    escape_next = False
                    continue
                    
                if char == '\\':
                    escape_next = True
                    continue
                    
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                    
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_str = full_response[start_idx:i+1]
                            try:
                                dashboard = json.loads(json_str)
                                # Check for Kibana saved object structure (title in attributes) or simple dashboard
                                if 'title' in dashboard or ('attributes' in dashboard and 'title' in dashboard.get('attributes', {})):
                                    logger.info(f"Successfully parsed dashboard JSON (length: {len(json_str)})")
                                    return dashboard
                            except:
                                pass
                            break
        
        # Method 3: Try simple strip
        json_str = full_response.strip()
        if json_str.startswith('{') and json_str.endswith('}'):
            try:
                dashboard = json.loads(json_str)
                # Check for Kibana saved object structure (title in attributes) or simple dashboard
                if 'title' in dashboard or ('attributes' in dashboard and 'title' in dashboard.get('attributes', {})):
                    return dashboard
            except:
                pass
        
        # If all methods fail, log the response for debugging
        logger.error(f"Failed to extract valid dashboard JSON from response")
        logger.error(f"Full response:\n{full_response}")
        return {'error': 'Could not extract valid dashboard JSON', 'raw_response': full_response}
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse dashboard JSON: {e}")
        logger.error(f"Response was: {full_response}")
        return {'error': 'Failed to parse dashboard JSON', 'raw_response': full_response}


def verify_pipeline_results(connection_id, inference_id, system_prompt, log_samples, pipeline, simulation_results):
    """
    Verify pipeline results using LLM
    
    Returns:
        Dict containing verification result
    """
    import re
    
    user_message = f"""Original Log Samples:
{json.dumps(log_samples[:10], indent=2)}

Pipeline Definition:
{json.dumps(pipeline, indent=2)}

Simulation Results:
{json.dumps(simulation_results, indent=2)}

Verify if the pipeline is correctly parsing the logs. Return ONLY the JSON verification object."""
    
    # Collect full response from LLM
    full_response = ""
    for chunk in stream_chat_completion(connection_id, inference_id, system_prompt, user_message):
        if 'error' in chunk:
            return {'error': chunk['error']}
        
        if 'choices' in chunk:
            for choice in chunk.get('choices', []):
                if 'delta' in choice and 'content' in choice['delta']:
                    full_response += choice['delta']['content']
                elif 'message' in choice and 'content' in choice['message']:
                    full_response += choice['message']['content']
    
    logger.info(f"Verifier response (first 500 chars): {full_response[:500]}")
    
    # Extract JSON from response
    try:
        # Method 1: Try to find complete JSON object by counting braces
        start_idx = full_response.find('{')
        if start_idx != -1:
            brace_count = 0
            for i, char in enumerate(full_response[start_idx:], start=start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        json_str = full_response[start_idx:i+1]
                        try:
                            verification = json.loads(json_str)
                            if 'is_valid' in verification:
                                return verification
                        except:
                            pass
                        break
        
        # Method 2: Extract from code blocks
        if '```json' in full_response:
            json_start = full_response.find('```json') + 7
            json_end = full_response.find('```', json_start)
            json_str = full_response[json_start:json_end].strip()
        elif '```' in full_response:
            json_start = full_response.find('```') + 3
            json_end = full_response.find('```', json_start)
            json_str = full_response[json_start:json_end].strip()
        else:
            json_str = full_response.strip()
        
        verification = json.loads(json_str)
        return verification
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse verification JSON: {e}")
        logger.error(f"Response was: {full_response}")
        return {'error': 'Failed to parse verification JSON', 'raw_response': full_response}


@require_http_methods(["GET"])
def get_models(request):
    """
    Get available inference models for a connection
    
    Query params:
        - connection_id: ID of the Elasticsearch connection
    
    Returns:
        JSON list of completion-type inference models
    """
    logger.info("get_models view called")
    try:
        connection_id = request.GET.get('connection_id')
        logger.info(f"connection_id from request: {connection_id}")
        
        if not connection_id:
            logger.warning("No connection_id provided")
            return JsonResponse({'error': 'Connection ID is required'}, status=400)
        
        models = get_inference_models(connection_id)
        logger.info(f"Returning {len(models)} models")
        return JsonResponse({'models': models})
        
    except Exception as e:
        logger.error(f"Error fetching models: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def classify_logs(request):
    """
    Step 1: Classify log samples to determine if we have an existing integration
    
    Accepts:
        - connection_id: ID of the Elasticsearch connection
        - inference_id: ID of the inference model to use
        - log_lines: Pasted log samples (optional)
        - log_file: Uploaded log file (optional)
    
    Returns:
        JSON response with classification result
    """
    try:
        connection_id = request.POST.get('connection_id')
        inference_id = request.POST.get('inference_id')
        log_lines = request.POST.get('log_lines', '')
        log_file = request.FILES.get('log_file')
        
        if not connection_id or not inference_id:
            return JsonResponse({'error': 'Connection ID and Inference model are required'}, status=400)
        
        if log_file:
            log_content = log_file.read().decode('utf-8')
        elif log_lines:
            log_content = log_lines
        else:
            return JsonResponse({'error': 'Please provide log samples'}, status=400)
        
        # Load the log classifier system prompt
        system_prompt_path = os.path.join(
            os.path.dirname(__file__),
            'system_prompts',
            'log_classifier.md'
        )
        
        try:
            with open(system_prompt_path, 'r', encoding='utf-8') as f:
                system_prompt = f.read()
        except FileNotFoundError:
            system_prompt = "You are an expert at analyzing log files and classifying them."
        
        # Load integrations list to include in the prompt
        integrations_path = os.path.join(
            os.path.dirname(__file__),
            'system_prompts',
            'integrations_list.json'
        )
        
        try:
            with open(integrations_path, 'r') as f:
                integrations = json.load(f)
                integrations_text = "\n".join([f"- {i['name']}: {i['description']}" for i in integrations])
                system_prompt += f"\n\n## Available Integrations (All {len(integrations)}):\n{integrations_text}"
        except FileNotFoundError:
            logger.warning("integrations_list.json not found")
        
        # Get a representative sample of log lines (up to 50 lines or 10000 chars, whichever is smaller)
        log_lines = log_content.split('\n')
        sample_lines = log_lines[:50]  # Take first 50 lines
        log_sample = '\n'.join(sample_lines)
        
        # If the sample is too large, truncate to 10000 chars
        if len(log_sample) > 10000:
            log_sample = log_sample[:10000]
        
        user_message = f"""Classify these log samples. Respond with ONLY the JSON object, no other text:

{log_sample}

Remember: Return ONLY the JSON object with has_integration, integration_name, format, and message fields."""
        
        # Collect the full response
        full_response = ""
        for chunk in stream_chat_completion(connection_id, inference_id, system_prompt, user_message):
            if 'error' in chunk:
                return JsonResponse({'error': chunk['error']}, status=500)
            
            if 'choices' in chunk:
                for choice in chunk.get('choices', []):
                    if 'delta' in choice and 'content' in choice['delta']:
                        full_response += choice['delta']['content']
                    elif 'message' in choice and 'content' in choice['message']:
                        full_response += choice['message']['content']
        
        logger.info(f"Raw LLM response: {full_response[:500]}")
        
        # Parse the JSON response from the LLM - try multiple extraction methods
        try:
            # Method 1: Try to find JSON object with curly braces
            import re
            json_match = re.search(r'\{[^{}]*"has_integration"[^{}]*\}', full_response, re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                classification = json.loads(json_str)
                return JsonResponse(classification)
            
            # Method 2: Extract from markdown code blocks
            if '```json' in full_response:
                json_start = full_response.find('```json') + 7
                json_end = full_response.find('```', json_start)
                json_str = full_response[json_start:json_end].strip()
            elif '```' in full_response:
                json_start = full_response.find('```') + 3
                json_end = full_response.find('```', json_start)
                json_str = full_response[json_start:json_end].strip()
            else:
                # Method 3: Try the whole response
                json_str = full_response.strip()
            
            classification = json.loads(json_str)
            return JsonResponse(classification)
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"Response was: {full_response}")
            return JsonResponse({
                'error': 'Failed to parse classification result',
                'raw_response': full_response
            }, status=500)
        
    except Exception as e:
        logger.error(f"Error classifying logs: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@require_http_methods(["POST"])
def generate_integration(request):
    """
    Generate and verify an Elasticsearch ingest pipeline using AI
    
    Steps:
    1. Generate pipeline JSON from LLM
    2. Simulate pipeline on sample logs
    3. Verify results with LLM
    4. If invalid, regenerate with feedback (max 3 attempts)
    
    Returns:
        JSON response with pipeline, verification results, and simulation output
    """
    try:
        connection_id = request.POST.get('connection_id')
        inference_id = request.POST.get('inference_id')
        log_lines = request.POST.get('log_lines', '')
        log_file = request.FILES.get('log_file')
        
        if not connection_id:
            return StreamingHttpResponse(
                iter(['<div class="alert alert-error"><span>Connection ID is required</span></div>']),
                content_type='text/html'
            )
        
        if not inference_id:
            return StreamingHttpResponse(
                iter(['<div class="alert alert-error"><span>Inference model is required</span></div>']),
                content_type='text/html'
            )
        
        if log_file:
            log_content = log_file.read().decode('utf-8')
        elif log_lines:
            log_content = log_lines
        else:
            return StreamingHttpResponse(
                iter(['<div class="alert alert-error"><span>Please provide log samples</span></div>']),
                content_type='text/html'
            )
        
        # Get classification result from request
        classification_json = request.POST.get('classification', '{}')
        
        try:
            classification = json.loads(classification_json)
        except json.JSONDecodeError:
            classification = {}
        
        # Parse log samples into list (use entire dataset for testing)
        log_samples = [line.strip() for line in log_content.split('\n') if line.strip()]
        
        # Load system prompts
        generator_prompt = load_system_prompt('ingest_pipeline_generator.md')
        verifier_prompt = load_system_prompt('ingest_verifier.md')
        
        # Attempt pipeline generation with verification loop (max 5 attempts)
        max_attempts = 5
        
        # Stream progressive updates during generation
        def attempt_generator():
            feedback = ""
            for attempt in range(1, max_attempts + 1):
                logger.info(f"Pipeline generation attempt {attempt}/{max_attempts}")
                
                # Send attempt start update
                yield json.dumps({
                    'step': 'generating',
                    'attempt': attempt,
                    'max_attempts': max_attempts
                }) + '\n'
                
                # Step 1: Generate pipeline
                pipeline_json = generate_pipeline_json(
                    connection_id, inference_id, generator_prompt,
                    classification, log_content, feedback
                )
                
                if 'error' in pipeline_json:
                    yield json.dumps({
                        'step': 'error',
                        'message': 'Failed to generate pipeline'
                    }) + '\n'
                    return
            
                # Send verification start update
                yield json.dumps({
                    'step': 'verifying',
                    'attempt': attempt,
                    'max_attempts': max_attempts
                }) + '\n'
                
                # Step 2: Simulate pipeline on sample logs
                try:
                    simulation_results = simulate_ingest_pipeline(
                        connection_id, pipeline_json, log_samples
                    )
                except Exception as e:
                    logger.error(f"Simulation failed: {e}")
                    # Extract error details for feedback
                    error_msg = str(e)
                    if 'No processor type exists with name' in error_msg:
                        invalid_processor = error_msg.split('[')[1].split(']')[0]
                        feedback = f"""Previous attempt failed simulation:

Error: {error_msg}

The pipeline uses an invalid processor type: '{invalid_processor}'. 

Elasticsearch ingest processors do not include 'mutate'. Valid processors are:
- grok, dissect, json, csv, xml (for parsing)
- date, set, remove, rename (for field manipulation)
- script (for complex transformations)
- append, foreach, join, split (for array operations)

Please fix the pipeline by removing '{invalid_processor}' and using only valid Elasticsearch ingest processors."""
                    else:
                        feedback = f"""Previous attempt failed simulation:

Error: {error_msg}

Please fix the pipeline and try again."""
                    
                    # Send attempt failed update
                    yield json.dumps({
                        'step': 'attempt_failed',
                        'attempt': attempt,
                        'error': error_msg,
                        'pipeline': pipeline_json
                    }) + '\n'
                    
                    # Continue to next attempt with feedback
                    logger.warning(f"Attempt {attempt} failed: {feedback}")
                    continue
                
                # Step 3: Verify results with LLM
                verification = verify_pipeline_results(
                    connection_id, inference_id, verifier_prompt,
                    log_samples, pipeline_json, simulation_results
                )
                
                if 'error' in verification:
                    yield json.dumps({
                        'step': 'error',
                        'message': 'Failed to verify pipeline'
                    }) + '\n'
                    return
                
                # Step 4: Check if valid
                if verification.get('is_valid', False):
                    logger.info(f"Pipeline validated successfully on attempt {attempt}")
                    
                    # Send verification success update with parsed documents
                    yield json.dumps({
                        'step': 'verified',
                        'verification': verification,
                        'attempts': attempt,
                        'simulation_results': simulation_results
                    }) + '\n'
                    
                    # Generate pipeline and template names based on classification
                    service_name = classification.get('integration_name', 'custom').lower().replace(' ', '-').replace('.', '-')
                    pipeline_name = f"logs-{service_name}-lsui"
                    template_name = f"logs-{service_name}-lsui"
                    data_stream_name = f"logs-{service_name}-lsui"
                    
                    # Continue with the rest of the progress generation
                    yield from create_integration_progress(connection_id, inference_id, pipeline_name, template_name, data_stream_name, pipeline_json, log_samples)
                    return
                else:
                    # Verification failed, prepare feedback for next attempt
                    feedback = f"""Previous attempt {attempt} failed verification:
                    
Verification result: {verification.get('message', 'No specific reason provided')}

Please fix the pipeline and try again."""
                    
                    yield json.dumps({
                        'step': 'verification_failed',
                        'attempt': attempt,
                        'error': verification.get('message', 'Verification failed'),
                        'pipeline': pipeline_json
                    }) + '\n'
                    
                    logger.warning(f"Attempt {attempt} verification failed: {feedback}")
                    continue
            
            # If we get here, all attempts failed
            yield json.dumps({
                'step': 'error',
                'message': f'Failed to generate valid pipeline after {max_attempts} attempts'
            }) + '\n'
        
        # Start the attempt generator
        return StreamingHttpResponse(attempt_generator(), content_type='application/json')
    
    except Exception as e:
        logger.error(f"Error generating integration: {e}", exc_info=True)
        return StreamingHttpResponse(
            iter([f'<div class="alert alert-error"><span>Error: {str(e)}</span></div>']),
            content_type='text/html'
        )


def create_integration_progress(connection_id, inference_id, pipeline_name, template_name, data_stream_name, pipeline_json, log_samples):
    """Continue with the rest of the integration creation process"""
    # Track created assets for cleanup on error
    created_assets = {
        'pipeline_name': None,
        'template_name': None,
        'data_stream_name': None,
        'dashboard_id': None
    }
    # Step 2: Create the ingest pipeline in Elasticsearch
    try:
        logger.info(f"Creating ingest pipeline: {pipeline_name}")
        create_ingest_pipeline(connection_id, pipeline_name, pipeline_json)
        created_assets['pipeline_name'] = pipeline_name
        yield json.dumps({
            'step': 'pipeline_created',
            'pipeline_name': pipeline_name,
            'pipeline': pipeline_json
        }) + '\n'
    except Exception as e:
        logger.error(f"Failed to create pipeline: {e}")
        yield json.dumps({
            'step': 'error',
            'message': f'Failed to create pipeline: {str(e)}',
            'assets': created_assets
        }) + '\n'
        return
    
    # Step 3: Generate index template
    template_prompt = load_system_prompt('template_creator.md')
    template_json = generate_index_template_json(
        connection_id, inference_id, template_prompt,
        log_samples, pipeline_json, pipeline_name
    )
                
    if 'error' in template_json:
        yield json.dumps({
            'step': 'error',
            'message': 'Failed to generate template'
        }) + '\n'
        return
    
    # Step 4: Create the index template in Elasticsearch
    try:
        logger.info(f"Creating index template: {template_name}")
        create_index_template(connection_id, template_name, template_json)
        created_assets['template_name'] = template_name
        yield json.dumps({
            'step': 'template_created',
            'template_name': template_name,
            'template': template_json
        }) + '\n'
    except Exception as e:
        logger.error(f"Failed to create template: {e}")
        yield json.dumps({
            'step': 'error',
            'message': f'Failed to create template: {str(e)}',
            'assets': created_assets
        }) + '\n'
        return
    
    # Step 5: Ingest all log samples to the data stream
    try:
        logger.info(f"Ingesting data to data stream: {data_stream_name}")
        ingest_response = ingest_to_data_stream(
            connection_id, data_stream_name, log_samples
        )
        created_assets['data_stream_name'] = data_stream_name
        yield json.dumps({
            'step': 'data_ingested',
            'data_stream_name': data_stream_name,
            'docs_ingested': len(log_samples),
            'errors': ingest_response.get('errors', False)
        }) + '\n'
    except Exception as e:
        logger.error(f"Failed to ingest data: {e}")
        yield json.dumps({
            'step': 'error',
            'message': f'Failed to ingest data: {str(e)}',
            'assets': created_assets
        }) + '\n'
        return
    
    # Steps 6-7: Generate and create Kibana dashboard with retry on API rejection
    dashboard_prompt = load_system_prompt('dashboard_generator.md')
    dashboard_feedback = ""
    dashboard_max_attempts = 3
    dashboard_result = None

    for dash_attempt in range(1, dashboard_max_attempts + 1):
        yield json.dumps({
            'step': 'generating_dashboard',
            'attempt': dash_attempt,
            'max_attempts': dashboard_max_attempts
        }) + '\n'

        dashboard_json = generate_dashboard_json(
            connection_id, inference_id, dashboard_prompt,
            data_stream_name, template_json, dashboard_feedback
        )

        if 'error' in dashboard_json:
            yield json.dumps({
                'step': 'error',
                'message': 'Failed to generate dashboard JSON',
                'assets': created_assets
            }) + '\n'
            return

        try:
            logger.info(f"Creating Kibana dashboard (attempt {dash_attempt}/{dashboard_max_attempts})")
            dashboard_result = create_kibana_dashboard(connection_id, dashboard_json)
            created_assets['dashboard_id'] = dashboard_result['id']
            yield json.dumps({
                'step': 'dashboard_created',
                'dashboard_id': dashboard_result['id'],
                'dashboard_url': dashboard_result['url'],
                'dashboard_json': dashboard_json
            }) + '\n'
            break  # success

        except Exception as e:
            error_str = str(e)
            logger.error(f"Dashboard creation attempt {dash_attempt}/{dashboard_max_attempts} failed: {error_str}")

            if dash_attempt < dashboard_max_attempts:
                dashboard_feedback = f"""Previous attempt {dash_attempt} was rejected by the Kibana API with this error:

{error_str[:1500]}

Fix the dashboard JSON. Common causes:
1. gauge / heatmap / tag_cloud use `metric` (singular object), not `metrics`
2. metric / pie / treemap / mosaic / waffle / data_table use `metrics` (plural array)
3. pie / treemap / mosaic / waffle must have a `group_by` array
4. data_table must have both `metrics` and `rows` arrays
5. xy: `data_source` must be INSIDE each layer object, not at config root
6. FORBIDDEN properties (cause 400): `anchor`, axis `label`, `breakdown`, `donut_hole`
7. `"column"` values must EXACTLY match ES|QL output column aliases

Return ONLY the corrected JSON object."""
                yield json.dumps({
                    'step': 'dashboard_attempt_failed',
                    'attempt': dash_attempt,
                    'error': error_str[:500]
                }) + '\n'
            else:
                yield json.dumps({
                    'step': 'error',
                    'message': f'Failed to create dashboard after {dashboard_max_attempts} attempts: {error_str[:300]}',
                    'assets': created_assets
                }) + '\n'
                return

    if dashboard_result is None:
        return
    
    # Step 8: Complete with asset information
    yield json.dumps({
        'step': 'complete',
        'assets': {
            'pipeline_name': pipeline_name,
            'template_name': template_name,
            'data_stream_name': data_stream_name,
            'dashboard_id': dashboard_result.get('id')
        }
    }) + '\n'


@csrf_exempt
@require_http_methods(["POST"])
def delete_integration_assets(request):
    """
    Delete all assets created during integration generation
    """
    try:
        data = json.loads(request.body)
        connection_id = data.get('connection_id')
        assets = data.get('assets', {})
        
        pipeline_name = assets.get('pipeline_name')
        template_name = assets.get('template_name')
        data_stream_name = assets.get('data_stream_name')
        dashboard_id = assets.get('dashboard_id')
        
        results = {
            'deleted': [],
            'failed': []
        }
        
        # Delete dashboard first
        if dashboard_id:
            try:
                delete_kibana_dashboard(connection_id, dashboard_id)
                results['deleted'].append(f'Dashboard: {dashboard_id}')
                logger.info(f"Deleted dashboard: {dashboard_id}")
            except Exception as e:
                results['failed'].append(f'Dashboard {dashboard_id}: {str(e)}')
                logger.error(f"Failed to delete dashboard {dashboard_id}: {e}")
        
        # Delete data stream
        if data_stream_name:
            try:
                delete_data_stream(connection_id, data_stream_name)
                results['deleted'].append(f'Data Stream: {data_stream_name}')
                logger.info(f"Deleted data stream: {data_stream_name}")
            except Exception as e:
                results['failed'].append(f'Data Stream {data_stream_name}: {str(e)}')
                logger.error(f"Failed to delete data stream {data_stream_name}: {e}")
        
        # Delete index template
        if template_name:
            try:
                delete_index_template(connection_id, template_name)
                results['deleted'].append(f'Index Template: {template_name}')
                logger.info(f"Deleted index template: {template_name}")
            except Exception as e:
                results['failed'].append(f'Index Template {template_name}: {str(e)}')
                logger.error(f"Failed to delete index template {template_name}: {e}")
        
        # Delete ingest pipeline
        if pipeline_name:
            try:
                delete_ingest_pipeline(connection_id, pipeline_name)
                results['deleted'].append(f'Ingest Pipeline: {pipeline_name}')
                logger.info(f"Deleted ingest pipeline: {pipeline_name}")
            except Exception as e:
                results['failed'].append(f'Ingest Pipeline {pipeline_name}: {str(e)}')
                logger.error(f"Failed to delete ingest pipeline {pipeline_name}: {e}")
        
        return JsonResponse({
            'success': len(results['failed']) == 0,
            'results': results
        })
        
    except Exception as e:
        logger.error(f"Error deleting integration assets: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def install_prebuilt_integration(request):
    """Install a prebuilt Fleet integration package"""
    try:
        data = json.loads(request.body)
        connection_id = data.get('connection_id')
        integration_name = data.get('integration_name')
        
        if not all([connection_id, integration_name]):
            return JsonResponse({
                'success': False,
                'error': 'Missing required parameters'
            }, status=400)
        
        # Load integrations list to get the version
        integrations_list_path = os.path.join(
            os.path.dirname(__file__), 
            'system_prompts', 
            'integrations_list.json'
        )
        
        version = None
        try:
            with open(integrations_list_path, 'r', encoding='utf-8') as f:
                integrations_list = json.load(f)
                for integration in integrations_list:
                    if integration.get('name') == integration_name:
                        version = integration.get('version')
                        break
        except Exception as e:
            logger.error(f"Failed to load integrations list: {e}")
            return JsonResponse({
                'success': False,
                'error': f'Failed to find integration version: {str(e)}'
            }, status=400)
        
        if not version:
            return JsonResponse({
                'success': False,
                'error': f'Integration "{integration_name}" not found in integrations list'
            }, status=404)
        
        logger.info(f"Installing prebuilt integration: {integration_name} v{version}")
        
        # Install the integration
        result = install_fleet_integration(connection_id, integration_name, version)
        
        # Extract assets from response
        response_data = result.get('response', {})
        items = response_data.get('items', [])
        
        # Get Kibana URL for dashboard links
        kibana_url = get_kibana_url(connection_id)
        
        # Separate dashboards from other assets and find data streams and pipelines
        dashboards = []
        other_assets = []
        data_streams = []
        ingest_pipelines = {}  # Map of data stream pattern to pipeline
        
        for item in items:
            item_type = item.get('type')
            if item_type == 'dashboard':
                dashboard_id = item.get('id')
                dashboards.append({
                    'id': dashboard_id,
                    'url': f"{kibana_url}/app/dashboards#/view/{dashboard_id}"
                })
            elif item_type == 'index_template':
                # Index templates define data streams
                # Format is typically: logs-{integration}.{dataset} or metrics-{integration}.{dataset}
                data_stream_name = item.get('id')
                if data_stream_name:
                    data_streams.append(data_stream_name)
            elif item_type == 'ingest_pipeline':
                # Ingest pipelines - format is typically: logs-{integration}.{dataset}-{version}
                pipeline_id = item.get('id')
                if pipeline_id:
                    # Extract the data stream pattern from pipeline name
                    # e.g., "logs-cisco_asa.log-3.23.0" -> "logs-cisco_asa.log"
                    parts = pipeline_id.rsplit('-', 1)  # Split off version
                    if len(parts) > 0:
                        ds_pattern = parts[0]
                        ingest_pipelines[ds_pattern] = pipeline_id
            
            other_assets.append(item)
        
        # Ingest sample data to the first data stream (if any)
        ingested_docs = 0
        target_data_stream = None
        target_pipeline = None
        ingestion_errors = []
        
        logger.info(f"Found {len(data_streams)} data streams: {data_streams}")
        logger.info(f"Found {len(ingest_pipelines)} ingest pipelines: {ingest_pipelines}")
        
        if data_streams:
            # Get log samples from request
            log_samples_json = data.get('log_samples', '[]')
            logger.info(f"Received log_samples_json type: {type(log_samples_json)}, length: {len(str(log_samples_json))}")
            
            try:
                log_samples = json.loads(log_samples_json) if isinstance(log_samples_json, str) else log_samples_json
                logger.info(f"Parsed log_samples: {len(log_samples)} samples")
                
                if log_samples:
                    # Use the first data stream (prefer logs over metrics)
                    logs_streams = [ds for ds in data_streams if ds.startswith('logs-')]
                    template_name = logs_streams[0] if logs_streams else data_streams[0]
                    
                    # The data stream name must preserve the dataset segment so the correct
                    # integration pipeline is applied as default_pipeline.
                    # e.g. template "logs-nginx.access" → data stream "logs-nginx.access-default"
                    #      template "logs-cisco_asa.log" → data stream "logs-cisco_asa.log-default"
                    target_data_stream = f"{template_name}-default"
                    
                    # Find the corresponding ingest pipeline using the template name (for logging)
                    target_pipeline = ingest_pipelines.get(template_name)
                    
                    logger.info(f"Ingesting {len(log_samples)} samples to {target_data_stream} (default pipeline: {target_pipeline})")
                    # Don't specify pipeline explicitly - let the data stream's default_pipeline handle it
                    ingest_response = ingest_to_data_stream(
                        connection_id, 
                        target_data_stream, 
                        log_samples
                    )
                    
                    # Check for ingestion errors
                    ingestion_errors = []
                    if ingest_response.get('errors'):
                        # Count successful vs failed
                        failed_count = 0
                        for item in ingest_response.get('items', []):
                            if 'error' in item.get('create', {}):
                                failed_count += 1
                                error_msg = item['create']['error'].get('reason', 'Unknown error')
                                if error_msg not in [e['message'] for e in ingestion_errors]:
                                    ingestion_errors.append({
                                        'message': error_msg,
                                        'type': item['create']['error'].get('type')
                                    })
                        ingested_docs = len(log_samples) - failed_count
                        logger.warning(f"Ingestion completed with {failed_count} failures, {ingested_docs} successful")
                    else:
                        ingested_docs = len(log_samples)
                        logger.info(f"Successfully ingested all {ingested_docs} documents")
                else:
                    logger.warning("No log samples to ingest")
            except Exception as e:
                logger.error(f"Failed to ingest sample data: {e}", exc_info=True)
                # Don't fail the whole operation if ingestion fails
        else:
            logger.warning("No data streams found to ingest to")
        
        return JsonResponse({
            'success': True,
            'integration_name': integration_name,
            'version': version,
            'dashboards': dashboards,
            'assets': other_assets,
            'total_assets': len(items),
            'ingested_docs': ingested_docs,
            'data_stream': target_data_stream,
            'ingestion_errors': ingestion_errors
        })
        
    except Exception as e:
        logger.error(f"Error installing prebuilt integration: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
