import React from 'react';
import { PipelineEditor } from './pipeline_editor';

export const EditorPage = (props) => {
  const { id } = useParams<{ id: string }>();

  try {
    return (
      <div>
        <h2>Editing pipeline: {id}</h2>
        <PipelineEditor pipelineId={id} {...props} />
      </div>
    );
  } catch (e) {
    console.error("EditorPage crashed:", e);
    return <div>Editor crashed: {String(e)}</div>;
  }
};
