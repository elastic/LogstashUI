#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.


def _apply_normalizers(normalizers):
    """
    Generate Logstash filter components from normalizer configurations.
    Groups normalizers by operation and scope for efficient processing.
    
    Args:
        normalizers: List of normalizer configurations from profile
        
    Returns:
        List of Logstash filter components
    """
    if not normalizers:
        return []
    
    filters = []
    
    # Group normalizers by operation, then by scope
    grouped = {}
    for normalizer in normalizers:
        operation = normalizer.get('operation')
        scope = normalizer.get('target', {}).get('scope')
        
        if not operation or not scope:
            continue
            
        if operation not in grouped:
            grouped[operation] = {}
        if scope not in grouped[operation]:
            grouped[operation][scope] = []
            
        grouped[operation][scope].append(normalizer)
    
    # Generate filters for each operation+scope group
    for operation, scopes in grouped.items():
        for scope, normalizer_list in scopes.items():
            if operation == 'multiply':
                if scope in ('get', 'table'):
                    filter_components = _generate_multiply_get_filter(normalizer_list)
                    if filter_components:
                        # Filter generators now return lists (comment + filter)
                        if isinstance(filter_components, list):
                            filters.extend(filter_components)
                        else:
                            filters.append(filter_components)
            elif operation == 'ratio':
                if scope in ('get', 'table'):
                    filter_components = _generate_ratio_get_filter(normalizer_list)
                    if filter_components:
                        # Filter generators now return lists (comment + filter)
                        if isinstance(filter_components, list):
                            filters.extend(filter_components)
                        else:
                            filters.append(filter_components)
            elif operation == 'translate':
                if scope in ('get', 'table'):
                    filter_components = _generate_translate_filter(normalizer_list)
                    if filter_components:
                        if isinstance(filter_components, list):
                            filters.extend(filter_components)
                        else:
                            filters.append(filter_components)
    
    return filters


def _generate_multiply_get_filter(normalizers):
    """
    Generate Ruby filter for multiply operations on get fields.
    Consolidates multiple multiply operations into a single Ruby filter.
    
    Args:
        normalizers: List of multiply normalizers for get scope
        
    Returns:
        Logstash filter component dict
    """
    if not normalizers:
        return None
    
    ruby_lines = []
    
    for normalizer in normalizers:
        field = normalizer.get('target', {}).get('field')
        multiply_value = normalizer.get('params', {}).get('multiply_value')
        
        if not field or multiply_value is None:
            continue
        
        # Convert dot-separated field to Logstash field path
        # e.g., "system.cpu.total.norm.pct" -> "[system][cpu][total][norm][pct]"
        field_parts = field.split('.')
        field_path = ''.join(f'[{part}]' for part in field_parts)
        
        # Generate Ruby code for this field
        ruby_lines.append(
            f'v = event.get("{field_path}")\n'
            f'if v\n'
            f'  event.set("{field_path}", v.to_f * {multiply_value})\n'
            f'end'
        )
    
    if not ruby_lines:
        return None
    
    ruby_code = '\n'.join(ruby_lines)
    
    # Build description of fields being multiplied
    field_list = []
    for normalizer in normalizers:
        field = normalizer.get('target', {}).get('field')
        multiply_value = normalizer.get('params', {}).get('multiply_value')
        if field and multiply_value is not None:
            field_list.append(f"  - {field} × {multiply_value}")
    
    comment_text = "Normalizer: Multiply\n"
    comment_text += "Multiplies field values by configured factors:\n"
    comment_text += '\n'.join(field_list)
    
    return [
        {
            "id": "normalizer_multiply_get_comment",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": comment_text
            }
        },
        {
            "id": "normalizer_multiply_get",
            "type": "filter",
            "plugin": "ruby",
            "config": {
                "code": ruby_code
            }
        }
    ]


def _generate_ratio_get_filter(normalizers):
    """
    Generate Ruby filter for ratio operations on get fields.
    Calculates ratios from two input fields and optionally creates total and ratio output fields.
    
    Args:
        normalizers: List of ratio normalizers for get scope
        
    Returns:
        Logstash filter component dict
    """
    if not normalizers:
        return None
    
    ruby_lines = []
    
    for idx, normalizer in enumerate(normalizers):
        params = normalizer.get('params', {})
        value1_field = params.get('value1_field')
        value2_field = params.get('value2_field')
        total_output = params.get('total_output_field', '').strip()
        ratio1_output = params.get('ratio1_output_field', '').strip()
        ratio2_output = params.get('ratio2_output_field', '').strip()
        complement_output = params.get('complement_ratio_output_field', '').strip()
        divide_output = params.get('divide_output_field', '').strip()

        if not value1_field or not value2_field:
            continue
        
        # Convert dot-separated fields to Logstash field paths
        value1_path = ''.join(f'[{part}]' for part in value1_field.split('.'))
        value2_path = ''.join(f'[{part}]' for part in value2_field.split('.'))
        
        # Use unique variable names for each ratio to avoid collisions
        var_suffix = f'_{idx}' if len(normalizers) > 1 else ''
        
        # Build Ruby code for this ratio calculation
        ruby_code_block = f'value1{var_suffix} = event.get("{value1_path}")\n'
        ruby_code_block += f'value2{var_suffix} = event.get("{value2_path}")\n\n'
        ruby_code_block += f'if value1{var_suffix} && value2{var_suffix}\n'
        ruby_code_block += f'  value1_f{var_suffix} = value1{var_suffix}.to_f\n'
        ruby_code_block += f'  value2_f{var_suffix} = value2{var_suffix}.to_f\n'
        ruby_code_block += f'  total_f{var_suffix} = value1_f{var_suffix} + value2_f{var_suffix}\n\n'
        ruby_code_block += f'  if total_f{var_suffix} > 0\n'
        
        # Add total output if specified
        if total_output:
            total_output_path = ''.join(f'[{part}]' for part in total_output.split('.'))
            ruby_code_block += f'    event.set("{total_output_path}", total_f{var_suffix})\n'
        
        # Add ratio1 output if specified
        if ratio1_output:
            ratio1_output_path = ''.join(f'[{part}]' for part in ratio1_output.split('.'))
            ruby_code_block += f'    event.set("{ratio1_output_path}", (value1_f{var_suffix} / total_f{var_suffix}))\n'
        
        # Add ratio2 output if specified
        if ratio2_output:
            ratio2_output_path = ''.join(f'[{part}]' for part in ratio2_output.split('.'))
            ruby_code_block += f'    event.set("{ratio2_output_path}", (value2_f{var_suffix} / total_f{var_suffix}))\n'

        # Add complement ratio output if specified: (value1 - value2) / value1
        # Useful when value1 is total and value2 is free/available, yielding used fraction.
        if complement_output:
            complement_output_path = ''.join(f'[{part}]' for part in complement_output.split('.'))
            ruby_code_block += f'    event.set("{complement_output_path}", (value1_f{var_suffix} - value2_f{var_suffix}) / value1_f{var_suffix})\n'

        # Add divide output if specified: value2 / value1
        if divide_output:
            divide_output_path = ''.join(f'[{part}]' for part in divide_output.split('.'))
            ruby_code_block += f'    event.set("{divide_output_path}", value2_f{var_suffix} / value1_f{var_suffix}) if value1_f{var_suffix} > 0\n'

        ruby_code_block += '  end\n'
        ruby_code_block += 'end'
        
        ruby_lines.append(ruby_code_block)
    
    if not ruby_lines:
        return None
    
    ruby_code = '\n\n'.join(ruby_lines)
    
    # Build description of ratio calculations
    calc_list = []
    for normalizer in normalizers:
        params = normalizer.get('params', {})
        value1_field = params.get('value1_field')
        value2_field = params.get('value2_field')
        total_output = params.get('total_output_field', '').strip()
        ratio1_output = params.get('ratio1_output_field', '').strip()
        ratio2_output = params.get('ratio2_output_field', '').strip()
        complement_output = params.get('complement_ratio_output_field', '').strip()
        divide_output = params.get('divide_output_field', '').strip()

        if value1_field and value2_field:
            calc_list.append(f"  Inputs: {value1_field}, {value2_field}")
            if total_output:
                calc_list.append(f"    → {total_output} = sum")
            if ratio1_output:
                calc_list.append(f"    → {ratio1_output} = value1 / (value1 + value2)")
            if ratio2_output:
                calc_list.append(f"    → {ratio2_output} = value2 / (value1 + value2)")
            if complement_output:
                calc_list.append(f"    → {complement_output} = (value1 - value2) / value1")
            if divide_output:
                calc_list.append(f"    → {divide_output} = value2 / value1")
    
    comment_text = "Normalizer: Ratio\n"
    comment_text += "Calculates ratios and derived fields from two input values:\n"
    comment_text += '\n'.join(calc_list)
    
    return [
        {
            "id": "normalizer_ratio_get_comment",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": comment_text
            }
        },
        {
            "id": "normalizer_ratio_get",
            "type": "filter",
            "plugin": "ruby",
            "config": {
                "code": ruby_code
            }
        }
    ]


def _generate_translate_filter(normalizers):
    """
    Generate Logstash translate plugin filters for value-mapping operations.
    Each normalizer produces its own translate filter that maps raw SNMP values
    (typically integers) to human-readable strings in-place.

    Args:
        normalizers: List of translate normalizers

    Returns:
        List of Logstash filter component dicts, or None
    """
    if not normalizers:
        return None

    components = []

    for normalizer in normalizers:
        field = normalizer.get('target', {}).get('field')
        mapping = normalizer.get('params', {}).get('mapping', {})

        if not field or not mapping:
            continue

        field_path = ''.join(f'[{part}]' for part in field.split('.'))

        pairs = ', '.join(f'{k}→{v}' for k, v in mapping.items())
        comment_text = f"Normalizer: Translate\nMaps {field}: {pairs}"

        components.append({
            "id": f"normalizer_translate_{field.replace('.', '_')}_comment",
            "type": "filter",
            "plugin": "comment",
            "config": {
                "text": comment_text
            }
        })
        components.append({
            "id": f"normalizer_translate_{field.replace('.', '_')}",
            "type": "filter",
            "plugin": "translate",
            "config": {
                "source": field_path,
                "destination": field_path,
                "dictionary": mapping,
                "override": True
            }
        })

    return components if components else None
