import { i18n } from '@kbn/i18n';
import type { AppMountParameters, CoreSetup, CoreStart, Plugin } from '@kbn/core/public';
import type {
  LogstashUiPluginSetup,
  LogstashUiPluginStart,
  AppPluginStartDependencies,
} from './types';
import { PLUGIN_NAME } from '../common';

export class LogstashUiPlugin implements Plugin<LogstashUiPluginSetup, LogstashUiPluginStart> {
  public setup(core: CoreSetup): LogstashUiPluginSetup {
    // Register an application into the side navigation menu
    core.application.register({
      id: 'logstashUi',
      title: PLUGIN_NAME,
      async mount(params: AppMountParameters) {
        // Load application bundle
        const { renderApp } = await import('./application');
        // Get start services as specified in kibana.json
        const [coreStart, depsStart] = await core.getStartServices();
        // Render the application
        return renderApp(coreStart, depsStart as AppPluginStartDependencies, params);
      },
    });

    // Return methods that should be available to other plugins
    return {
      getGreeting() {
        return i18n.translate('logstashUi.greetingText', {
          defaultMessage: 'Hello from {name}!',
          values: {
            name: PLUGIN_NAME,
          },
        });
      },
    };
  }

  public start(core: CoreStart): LogstashUiPluginStart {
    return {};
  }

  public stop() {}
}
