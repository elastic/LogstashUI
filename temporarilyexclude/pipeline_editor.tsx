// public/components/pipeline_editor.tsx
import React, { useState } from 'react';
import { EuiPageTemplate, EuiTitle, EuiText, EuiSpacer } from '@elastic/eui';

interface PipelineEditorProps {
  pipelineId: string;
}

export const PipelineEditor = ({ pipelineId }: PipelineEditorProps) => {
  // TODO: replace this with a real pipeline structure
  const [stages, setStages] = useState([
    { id: 'input-1', type: 'input', description: 'Beats input' },
    { id: 'filter-1', type: 'filter', description: 'Grok filter' },
    { id: 'output-1', type: 'output', description: 'Elasticsearch output' },
  ]);

  return (
    <EuiPageTemplate restrictWidth="1000px">
      <EuiPageTemplate.Header>
        <EuiTitle size="l">
          <h1>Editing pipeline: {pipelineId}</h1>
        </EuiTitle>
      </EuiPageTemplate.Header>

      <EuiPageTemplate.Section>
        <EuiText>
          <p>
            This is a placeholder editor. Later you’ll add drag-and-drop, visual connectors, and
            configuration forms for each stage.
          </p>
        </EuiText>

        <EuiSpacer size="l" />

        {stages.map((stage) => (
          <div key={stage.id}>
            <EuiTitle size="s">
              <h3>
                {stage.type.toUpperCase()}: {stage.description}
              </h3>
            </EuiTitle>
            <EuiSpacer size="m" />
          </div>
        ))}
      </EuiPageTemplate.Section>
    </EuiPageTemplate>
  );
};
