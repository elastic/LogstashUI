import React from 'react';
import { PipelinesTable } from '../components/pipelines_table';

export const PipelinesPage = (props) => {
  return (
    <div>
      <h2>Logstash Pipelines</h2>
      <PipelinesTable {...props} />
    </div>
  );
};
