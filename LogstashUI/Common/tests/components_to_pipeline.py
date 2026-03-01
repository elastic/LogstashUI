from Common.logstash_config_parse import ComponentToPipeline, logstash_config_to_components
import pytest
import json
import os

# Load test cases from external files
def load_test_cases():
    """Load test cases from conversion_data directory."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pipelines_dir = os.path.join(base_dir, "conversion_data", "pipelines")
    components_dir = os.path.join(base_dir, "conversion_data", "components")
    
    test_cases = []
    
    # Get all .conf files
    for filename in sorted(os.listdir(pipelines_dir)):
        if filename.endswith('.conf'):
            name = filename[:-5]  # Remove .conf extension
            
            # Load pipeline config
            pipeline_file = os.path.join(pipelines_dir, filename)
            with open(pipeline_file, 'r', encoding='utf-8') as f:
                pipeline = f.read()
            
            # Load components JSON
            components_file = os.path.join(components_dir, f"{name}.json")
            with open(components_file, 'r', encoding='utf-8') as f:
                components = f.read()
            
            test_cases.append((name, pipeline, components))
    
    return test_cases

test_cases = load_test_cases()



@pytest.mark.parametrize(
    "name, pipeline, components",
    test_cases,
    ids=[case[0] for case in test_cases]
)
def test_components_to_config(name, pipeline, components):
    """
    Test that ComponentToPipeline can generate a pipeline config from components.
    Compares the original pipeline with the generated pipeline from stored components.
    """
    # Load the stored components and convert to pipeline
    parser = ComponentToPipeline(json.loads(components))
    generated_pipeline = parser.components_to_logstash_config()
    
    # Compare the original pipeline with the generated one
    assert pipeline == generated_pipeline
