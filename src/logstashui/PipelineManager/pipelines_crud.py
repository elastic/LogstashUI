#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.http import JsonResponse, HttpResponse
from django.conf import settings

from Common.logstash_utils import get_logstash_pipeline
from Common.validators import validate_pipeline_name
from Common.decorators import require_admin_role
from Common.elastic_utils import get_elastic_connection

from PipelineManager.models import Policy, Pipeline, Connection as ConnectionTable

from datetime import datetime, timezone

import requests
import logging
import json

logger = logging.getLogger(__name__)

@require_admin_role
def UpdatePipelineSettings(request):
    if request.method == "POST":
        try:
            es_id = request.POST.get("es_id")
            ls_id = request.POST.get("ls_id")
            pipeline_name = request.POST.get("pipeline")

            # Validate required fields - need either es_id or ls_id
            if not (es_id or ls_id) or not pipeline_name:
                return HttpResponse(
                    'Error: Missing pipeline ID or connection ID',
                    status=400
                )

            # Validate pipeline name
            is_valid, error_msg = validate_pipeline_name(pipeline_name)
            if not is_valid:
                return HttpResponse(error_msg, status=400)

            # Get form values
            description = request.POST.get("description", "")
            pipeline_workers = request.POST.get("pipeline_workers")
            pipeline_batch_size = request.POST.get("pipeline_batch_size")
            pipeline_batch_delay = request.POST.get("pipeline_batch_delay")
            queue_type = request.POST.get("queue_type")
            queue_max_bytes = request.POST.get("queue_max_bytes")
            queue_max_bytes_unit = request.POST.get("queue_max_bytes_unit")
            queue_checkpoint_writes = request.POST.get("queue_checkpoint_writes")

            # Handle ls_id (agent pipeline) vs es_id (centralized pipeline)
            if ls_id:
                # Update Pipeline model for agent policy
                try:
                    pipeline_obj = Pipeline.objects.get(policy_id=ls_id, name=pipeline_name)

                    # Update fields
                    if description is not None:
                        pipeline_obj.description = description
                    if pipeline_workers:
                        pipeline_obj.pipeline_workers = int(pipeline_workers)
                    if pipeline_batch_size:
                        pipeline_obj.pipeline_batch_size = int(pipeline_batch_size)
                    if pipeline_batch_delay:
                        pipeline_obj.pipeline_batch_delay = int(pipeline_batch_delay)
                    if queue_type:
                        pipeline_obj.queue_type = queue_type
                    if queue_max_bytes is not None and queue_max_bytes != '' and queue_max_bytes_unit:
                        pipeline_obj.queue_max_bytes = f"{queue_max_bytes}{queue_max_bytes_unit}"
                    if queue_checkpoint_writes:
                        pipeline_obj.queue_checkpoint_writes = int(queue_checkpoint_writes)

                    pipeline_obj.save()

                    # Mark policy as having undeployed changes
                    policy = Policy.objects.get(pk=ls_id)
                    policy.has_undeployed_changes = True
                    policy.save(update_fields=['has_undeployed_changes'])

                    logger.info(
                        f"User '{request.user.username}' updated settings for pipeline '{pipeline_name}' in policy {ls_id}")
                    return HttpResponse('', status=200)

                except Pipeline.DoesNotExist:
                    return HttpResponse(f"Pipeline '{pipeline_name}' not found in policy {ls_id}", status=404)
            else:
                # Update centralized pipeline via Elasticsearch
                current_pipeline_config = get_logstash_pipeline(es_id, pipeline_name)
                settings_body = {
                    "pipeline": current_pipeline_config['pipeline'],
                    "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                    "pipeline_metadata": {
                        "version": current_pipeline_config['pipeline_metadata']['version'] + 1,
                        "type": "logstash_pipeline"
                    },
                    "username": "logstashui",
                    "pipeline_settings": {},
                }

                if 'description' in current_pipeline_config:
                    settings_body['description'] = current_pipeline_config['description']

                if description:
                    settings_body["description"] = description
                if pipeline_workers:
                    settings_body['pipeline_settings']["pipeline.workers"] = int(pipeline_workers)
                if pipeline_batch_size:
                    settings_body['pipeline_settings']["pipeline.batch.size"] = int(pipeline_batch_size)
                if pipeline_batch_delay:
                    settings_body['pipeline_settings']["pipeline.batch.delay"] = int(pipeline_batch_delay)
                if queue_type:
                    settings_body['pipeline_settings']["queue.type"] = queue_type
                if queue_max_bytes is not None and queue_max_bytes != '' and queue_max_bytes_unit:
                    settings_body['pipeline_settings']["queue.max_bytes"] = f"{queue_max_bytes}{queue_max_bytes_unit}"
                if queue_checkpoint_writes:
                    settings_body['pipeline_settings']["queue.checkpoint.writes"] = int(queue_checkpoint_writes)

                # Get Elasticsearch connection and update pipeline settings
                es = get_elastic_connection(es_id)
                es.logstash.put_pipeline(id=pipeline_name, body=settings_body)

                logger.info(
                    f"User '{request.user.username}' updated settings for pipeline '{pipeline_name}' (Connection ID: {es_id})")
                return HttpResponse('', status=200)

        except Exception as e:
            # Return simple error message - toast notification handled by JavaScript
            logger.error(f"Error updating pipeline settings: {str(e)}")
            return HttpResponse(str(e), status=500)

    return HttpResponse('Invalid request method', status=405)


@require_admin_role
def CreatePipeline(request, simulate=False, pipeline_name=None, pipeline_config=None):
    """
    Create a pipeline in Elasticsearch, LogstashAgent, or Django Pipeline model.

    Args:
        request: Django request object
        simulate: If True, send to logstashagent instead of Elasticsearch
        pipeline_name: Pipeline name (used when called directly for simulation)
        pipeline_config: Pipeline config string (used when called directly for simulation)
    """

    if request.method == "POST" or simulate:
        # Get parameters from POST or function arguments
        if not simulate:
            es_id = request.POST.get("es_id")
            policy_id = request.POST.get("policy_id")
            pipeline_name = request.POST.get("pipeline")
            pipeline_config = request.POST.get("pipeline_config", "").strip()
        else:
            es_id = None
            policy_id = None

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Use provided config or default empty config
        if pipeline_config:
            pipeline_content = pipeline_config
        else:
            pipeline_content = "input {}\nfilter {}\noutput {}"

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Create pipeline in Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)

                # Check if pipeline already exists
                if Pipeline.objects.filter(policy=policy, name=pipeline_name).exists():
                    return HttpResponse("A pipeline already exists with that name", status=400)

                # Create the pipeline (hash will be computed automatically by the model's save method)
                pipeline = Pipeline.objects.create(
                    policy=policy,
                    name=pipeline_name,
                    description="",
                    lscl=pipeline_content
                )

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.info(
                    f"User '{request.user.username}' created pipeline '{pipeline_name}' in policy '{policy.name}' (ID: {policy_id})")

                # Return success response - redirect to pipeline editor (same as centralized)
                response = HttpResponse("Pipeline created successfully!", status=200)
                response[
                    'HX-Redirect'] = f'/ConnectionManager/Pipelines/Editor/?ls_id={policy_id}&pipeline={pipeline_name}'
                return response

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Exception as e:
                logger.error(f"Failed to create pipeline in policy: {e}")
                return HttpResponse(f"Failed to create pipeline: {str(e)}", status=500)

        # Build the pipeline body for Elasticsearch/LogstashAgent
        pipeline_body = {
            "pipeline": pipeline_content,
            "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
            "pipeline_metadata": {
                "version": 1,
                "type": "logstash_pipeline"
            },
            "username": "logstashui",
            "pipeline_settings": {
                "pipeline.batch.delay": 50,
                "pipeline.batch.size": 125,
                "pipeline.workers": 1,
                "queue.checkpoint.writes": 1024,
                "queue.max_bytes": "1gb",
                "queue.type": "memory"
            },
            "description": ""
        }

        if simulate:
            # Send to logstashagent
            logstash_agent_url = f"{settings.LOGSTASH_AGENT_URL}/_logstash/pipeline/{pipeline_name}"

            try:
                response = requests.put(
                    logstash_agent_url,
                    json=pipeline_body,
                    verify=False,  # --insecure equivalent
                    timeout=10
                )
                response.raise_for_status()
                logger.info(
                    f"User '{request.user.username}' created simulation pipeline '{pipeline_name}' in logstashagent")
                return HttpResponse("Simulation pipeline created successfully!", status=200)
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to create simulation pipeline in logstashagent: {e}")
                return HttpResponse(f"Failed to create simulation pipeline: {str(e)}", status=500)
        elif es_id:
            # Send to Elasticsearch (centralized pipeline management)
            es = get_elastic_connection(es_id)
            pipeline_doc = es.logstash.put_pipeline(
                id=pipeline_name,
                body=pipeline_body
            )

            logger.info(
                f"User '{request.user.username}' created new pipeline '{pipeline_name}' (Connection ID: {es_id})")
            response = HttpResponse("Pipeline created successfully!")
            response['HX-Redirect'] = f'/ConnectionManager/Pipelines/Editor/?es_id={es_id}&pipeline={pipeline_name}'
            return response
        else:
            # No valid context provided
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


@require_admin_role
def DeletePipeline(request):
    if request.method == "POST":
        # Handle both JSON and form data
        if request.content_type == 'application/json':
            data = json.loads(request.body)
            es_id = data.get("es_id")
            pipeline_name = data.get("pipeline")
            policy_id = data.get("policy_id")
        else:
            es_id = request.POST.get("es_id")
            pipeline_name = request.POST.get("pipeline")
            policy_id = request.POST.get("policy_id")

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Delete from Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)
                pipeline = Pipeline.objects.get(policy=policy, name=pipeline_name)
                pipeline.delete()

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.warning(
                    f"User '{request.user.username}' deleted pipeline '{pipeline_name}' from policy '{policy.name}' (ID: {policy_id})")
                return HttpResponse(status=204)

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Pipeline.DoesNotExist:
                return HttpResponse(f"Pipeline '{pipeline_name}' not found in this policy.", status=404)
            except Exception as e:
                logger.error(f"Failed to delete pipeline from policy: {e}")
                return HttpResponse(f"Failed to delete pipeline: {str(e)}", status=500)

        elif es_id:
            # Delete from Elasticsearch for centralized pipeline management
            try:
                es = get_elastic_connection(es_id)
                es.logstash.delete_pipeline(id=pipeline_name)

                logger.warning(
                    f"User '{request.user.username}' deleted pipeline '{pipeline_name}' (Connection ID: {es_id})")
                return HttpResponse(status=204)
            except Exception as e:
                logger.error(f"Failed to delete pipeline from Elasticsearch: {e}")
                return HttpResponse(f"Failed to delete pipeline: {str(e)}", status=500)
        else:
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


@require_admin_role
def ClonePipeline(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        policy_id = request.POST.get("policy_id")
        source_pipeline = request.POST.get("source_pipeline")
        new_pipeline = request.POST.get("new_pipeline")

        # Debug logging
        logger.info(
            f"ClonePipeline called with: es_id={es_id}, policy_id={policy_id}, source={source_pipeline}, new={new_pipeline}")

        # Validate source pipeline name
        is_valid, error_msg = validate_pipeline_name(source_pipeline)
        if not is_valid:
            return HttpResponse(f"Invalid source pipeline name: {error_msg}", status=400)

        # Validate new pipeline name
        is_valid, error_msg = validate_pipeline_name(new_pipeline)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Clone within Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)

                # Get the source pipeline
                try:
                    source = Pipeline.objects.get(policy=policy, name=source_pipeline)
                except Pipeline.DoesNotExist:
                    return HttpResponse(f"Source pipeline '{source_pipeline}' not found in this policy.", status=404)

                # Check if new pipeline name already exists
                if Pipeline.objects.filter(policy=policy, name=new_pipeline).exists():
                    # Return 400 status so HTMX triggers response-error event
                    return HttpResponse("A pipeline already exists with that name", status=400)

                # Create the cloned pipeline
                Pipeline.objects.create(
                    policy=policy,
                    name=new_pipeline,
                    description=f"Cloned from {source_pipeline}",
                    lscl=source.lscl
                )

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.info(
                    f"User '{request.user.username}' cloned pipeline '{source_pipeline}' to '{new_pipeline}' in policy '{policy.name}' (ID: {policy_id})")

                # Return success with HX-Trigger to refresh the list
                # Get the connection ID from the policy to trigger the correct event
                connection = ConnectionTable.objects.filter(policy=policy).first()
                connection_id = connection.id if connection else es_id
                response = HttpResponse("Pipeline cloned successfully!", status=200)
                response['HX-Trigger'] = f'pipelineCloned-{connection_id}'
                return response

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Exception as e:
                logger.error(f"Failed to clone pipeline in policy: {e}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Failed to clone pipeline: {str(e)}", status=500)

        elif es_id:
            # Clone in Elasticsearch for centralized pipeline management
            try:
                es = get_elastic_connection(es_id)

                # Get the source pipeline configuration
                source_config = es.logstash.get_pipeline(id=source_pipeline)

                if source_pipeline not in source_config:
                    return HttpResponse(f"Source pipeline '{source_pipeline}' not found", status=404)

                source_data = source_config[source_pipeline]

                # Check if new pipeline name already exists
                existing_pipelines = es.logstash.get_pipeline()
                if new_pipeline in existing_pipelines:
                    return HttpResponse("A pipeline already exists with that name", status=400)

                # Create the new pipeline with the same configuration as the source
                es.logstash.put_pipeline(
                    id=new_pipeline,
                    body={
                        "pipeline": source_data['pipeline'],
                        "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                        "pipeline_metadata": {
                            "version": 1,
                            "type": "logstash_pipeline"
                        },
                        "username": "logstashui",
                        "pipeline_settings": source_data.get('pipeline_settings', {}),
                        "description": source_data.get('description', f"Cloned from {source_pipeline}")
                    }
                )

                logger.info(
                    f"User '{request.user.username}' cloned pipeline '{source_pipeline}' to '{new_pipeline}' (Connection ID: {es_id})")

                # Return success with HX-Trigger to refresh the list
                response = HttpResponse("Pipeline cloned successfully!", status=200)
                response['HX-Trigger'] = f'pipelineCloned-{es_id}'
                return response

            except Exception as e:
                logger.error(f"Error cloning pipeline: {str(e)}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Error cloning pipeline: {str(e)}", status=500)
        else:
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


@require_admin_role
def RenamePipeline(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        policy_id = request.POST.get("policy_id")
        source_pipeline = request.POST.get("source_pipeline")
        new_pipeline = request.POST.get("new_pipeline")

        # Debug logging
        logger.info(
            f"RenamePipeline called with: es_id={es_id}, policy_id={policy_id}, source={source_pipeline}, new={new_pipeline}")

        # Validate source pipeline name
        is_valid, error_msg = validate_pipeline_name(source_pipeline)
        if not is_valid:
            return HttpResponse(f"Invalid source pipeline name: {error_msg}", status=400)

        # Validate new pipeline name
        is_valid, error_msg = validate_pipeline_name(new_pipeline)
        if not is_valid:
            return HttpResponse(error_msg, status=400)

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Rename within Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)

                # Get the source pipeline
                try:
                    source = Pipeline.objects.get(policy=policy, name=source_pipeline)
                except Pipeline.DoesNotExist:
                    return HttpResponse(f"Source pipeline '{source_pipeline}' not found in this policy.", status=404)

                # Check if new pipeline name already exists
                if Pipeline.objects.filter(policy=policy, name=new_pipeline).exists():
                    return HttpResponse("A pipeline already exists with that name", status=400)

                # Create the renamed pipeline (clone)
                Pipeline.objects.create(
                    policy=policy,
                    name=new_pipeline,
                    description=source.description,
                    lscl=source.lscl
                )

                # Delete the original pipeline
                source.delete()

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.info(
                    f"User '{request.user.username}' renamed pipeline '{source_pipeline}' to '{new_pipeline}' in policy '{policy.name}' (ID: {policy_id})")

                # Return success with HX-Trigger to refresh the list
                # Get the connection ID from the policy to trigger the correct event
                connection = ConnectionTable.objects.filter(policy=policy).first()
                connection_id = connection.id if connection else es_id
                response = HttpResponse("Pipeline renamed successfully!", status=200)
                response['HX-Trigger'] = f'pipelineRenamed-{connection_id}'
                return response

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Exception as e:
                logger.error(f"Failed to rename pipeline in policy: {e}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Failed to rename pipeline: {str(e)}", status=500)

        elif es_id:
            # Rename in Elasticsearch for centralized pipeline management
            try:
                es = get_elastic_connection(es_id)

                # Get the source pipeline configuration
                source_config = es.logstash.get_pipeline(id=source_pipeline)

                if source_pipeline not in source_config:
                    return HttpResponse(f"Source pipeline '{source_pipeline}' not found", status=404)

                source_data = source_config[source_pipeline]

                # Check if new pipeline name already exists
                existing_pipelines = es.logstash.get_pipeline()
                if new_pipeline in existing_pipelines:
                    return HttpResponse("A pipeline already exists with that name", status=400)

                # Create the new pipeline with the same configuration as the source
                es.logstash.put_pipeline(
                    id=new_pipeline,
                    body={
                        "pipeline": source_data['pipeline'],
                        "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                        "pipeline_metadata": {
                            "version": 1,
                            "type": "logstash_pipeline"
                        },
                        "username": "logstashui",
                        "pipeline_settings": source_data.get('pipeline_settings', {}),
                        "description": source_data.get('description', '')
                    }
                )

                # Delete the original pipeline
                es.logstash.delete_pipeline(id=source_pipeline)

                logger.info(
                    f"User '{request.user.username}' renamed pipeline '{source_pipeline}' to '{new_pipeline}' (Connection ID: {es_id})")

                # Return success with HX-Trigger to refresh the list
                response = HttpResponse("Pipeline renamed successfully!", status=200)
                response['HX-Trigger'] = f'pipelineRenamed-{es_id}'
                return response

            except Exception as e:
                logger.error(f"Error renaming pipeline: {str(e)}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Error renaming pipeline: {str(e)}", status=500)
        else:
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


@require_admin_role
def UpdatePipelineDescription(request):
    if request.method == "POST":
        es_id = request.POST.get("es_id")
        policy_id = request.POST.get("policy_id")
        pipeline_name = request.POST.get("pipeline_name")
        description = request.POST.get("description", "")

        # Debug logging
        logger.info(
            f"UpdatePipelineDescription called with: es_id={es_id}, policy_id={policy_id}, pipeline={pipeline_name}")

        # Validate pipeline name
        is_valid, error_msg = validate_pipeline_name(pipeline_name)
        if not is_valid:
            return HttpResponse(f"Invalid pipeline name: {error_msg}", status=400)

        # Determine context: policy_id means agent policy pipeline, es_id means centralized
        if policy_id:
            # Update description in Django Pipeline model for agent policy
            try:
                policy = Policy.objects.get(pk=policy_id)

                # Get the pipeline
                try:
                    pipeline = Pipeline.objects.get(policy=policy, name=pipeline_name)
                except Pipeline.DoesNotExist:
                    return HttpResponse(f"Pipeline '{pipeline_name}' not found in this policy.", status=404)

                # Update the description
                pipeline.description = description
                pipeline.save()

                # Mark policy as having undeployed changes
                policy.has_undeployed_changes = True
                policy.save()

                logger.info(
                    f"User '{request.user.username}' updated description for pipeline '{pipeline_name}' in policy '{policy.name}' (ID: {policy_id})")

                # Return success with HX-Trigger to refresh the list
                connection = ConnectionTable.objects.filter(policy=policy).first()
                connection_id = connection.id if connection else es_id
                response = HttpResponse("Pipeline description updated successfully!", status=200)
                response['HX-Trigger'] = f'pipelineDescriptionUpdated-{connection_id}'
                return response

            except Policy.DoesNotExist:
                return HttpResponse(f"Policy with ID {policy_id} not found.", status=404)
            except Exception as e:
                logger.error(f"Failed to update pipeline description in policy: {e}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Failed to update pipeline description: {str(e)}", status=500)

        elif es_id:
            # Update description in Elasticsearch for centralized pipeline management
            try:
                es = get_elastic_connection(es_id)

                # Get the current pipeline configuration
                current_config = es.logstash.get_pipeline(id=pipeline_name)

                if pipeline_name not in current_config:
                    return HttpResponse(f"Pipeline '{pipeline_name}' not found", status=404)

                current_data = current_config[pipeline_name]

                # Update the pipeline with new description
                es.logstash.put_pipeline(
                    id=pipeline_name,
                    body={
                        "pipeline": current_data['pipeline'],
                        "last_modified": datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%f')[:-3] + 'Z',
                        "pipeline_metadata": {
                            "version": current_data['pipeline_metadata'].get('version', 1) + 1,
                            "type": "logstash_pipeline"
                        },
                        "username": "logstashui",
                        "pipeline_settings": current_data.get('pipeline_settings', {}),
                        "description": description
                    }
                )

                logger.info(
                    f"User '{request.user.username}' updated description for pipeline '{pipeline_name}' (Connection ID: {es_id})")

                # Return success with HX-Trigger to refresh the list
                response = HttpResponse("Pipeline description updated successfully!", status=200)
                response['HX-Trigger'] = f'pipelineDescriptionUpdated-{es_id}'
                return response

            except Exception as e:
                logger.error(f"Error updating pipeline description: {str(e)}")
                import traceback
                traceback.print_exc()
                return HttpResponse(f"Error updating pipeline description: {str(e)}", status=500)
        else:
            return HttpResponse("Invalid request: neither policy_id nor es_id provided", status=400)


def GetPipeline(request):
    if request.method == "GET":
        es_id = request.GET.get("es_id")
        pipeline_name = request.GET.get("pipeline")

        # Validate required parameters
        if not es_id or not pipeline_name:
            return JsonResponse({"error": "Missing required parameters: es_id and pipeline"}, status=400)

        pipeline_config = get_logstash_pipeline(es_id, pipeline_name)

        # Handle case where pipeline couldn't be fetched
        if not pipeline_config:
            return JsonResponse({"error": f"Could not fetch pipeline '{pipeline_name}' from connection {es_id}"},
                                status=400)

        pipeline_string = pipeline_config['pipeline']

        return JsonResponse({"code": pipeline_string})

