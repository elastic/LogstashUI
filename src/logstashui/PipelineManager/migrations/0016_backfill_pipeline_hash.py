#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import hashlib
from django.db import migrations


def backfill_pipeline_hash(apps, schema_editor):
    Pipeline = apps.get_model('PipelineManager', 'Pipeline')
    to_update = []
    for pipeline in Pipeline.objects.all():
        hash_input = (
            f"{pipeline.name}{pipeline.lscl}{pipeline.pipeline_workers}"
            f"{pipeline.pipeline_batch_size}{pipeline.pipeline_batch_delay}"
            f"{pipeline.queue_type}{pipeline.queue_max_bytes}"
            f"{pipeline.queue_checkpoint_writes}"
        )
        pipeline.pipeline_hash = hashlib.sha256(hash_input.encode('utf-8')).hexdigest()
        to_update.append(pipeline)
    Pipeline.objects.bulk_update(to_update, ['pipeline_hash'])


class Migration(migrations.Migration):

    dependencies = [
        ('PipelineManager', '0015_add_pipeline_hash'),
    ]

    operations = [
        migrations.RunPython(backfill_pipeline_hash, migrations.RunPython.noop),
    ]
