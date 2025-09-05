import React from 'react';
import { Route, Routes, Navigate } from '@kbn/shared-ux-router';
import { PipelinesPage } from '../pages/pipelines';
import { EditorPage } from '../pages/editor';

export const LogstashUiApp = (props) => {
  return (
    <Routes>
      <Route path="/" element={<PipelinesPage {...props} />} />
      <Route path="/editor/:id" element={<EditorPage {...props} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
};
