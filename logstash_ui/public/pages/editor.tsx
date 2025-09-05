import React from 'react';
import { useParams } from '@kbn/shared-ux-router';
import { PipelineEditor } from '../components/pipeline_editor';

export const EditorPage = (props) => {
  const { id } = useParams<{ id: string }>();

  return (
    <div>
      <h2>Editing pipeline: {id}</h2>
      <PipelineEditor pipelineId={id} {...props} />
    </div>
  );
};
