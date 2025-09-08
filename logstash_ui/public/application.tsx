import React from 'react';
import ReactDOM from 'react-dom';
import { Router } from '@kbn/shared-ux-router';
import type { AppMountParameters, CoreStart } from '@kbn/core/public';
import type { AppPluginStartDependencies } from './types';
import { LogstashUiApp } from './components/app';

export const renderApp = (
  core: CoreStart,
  deps: AppPluginStartDependencies,
  { appBasePath, element, history }: AppMountParameters
) => {
  ReactDOM.render(
    <Router history={history} basename={appBasePath}>
      <LogstashUiApp
        basename={appBasePath}
        history={history}
        http={core.http}
        notifications={core.notifications}
      />
    </Router>,
    element
  );

  return () => ReactDOM.unmountComponentAtNode(element);
};
