import React from 'react';
import { PipelinesPage } from '../pages/pipelines';
import type { CoreStart } from '@kbn/core/public';

interface LogstashUiAppProps {
  basename: string;
  history: any;
  http: CoreStart['http'];
  notifications: CoreStart['notifications'];
}

export const LogstashUiApp: React.FC<LogstashUiAppProps> = ({
  basename,
  history,
  http,
  notifications,
}) => {
  console.log('HITTING APP! LogstashUiApp props:', basename);

  const path = window.location.pathname;
  const subPath = path.replace(/^.*\/app\/logstashUi/, '');

  if (subPath.startsWith('/test')) {
    return <h2>Hit TEST route</h2>;
  }

  return <PipelinesPage http={http} notifications={notifications} />;
};
