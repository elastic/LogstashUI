import type {
  PluginInitializerContext,
  CoreSetup,
  CoreStart,
  Plugin,
  Logger,
} from '@kbn/core/server';

import type { LogstashUiPluginSetup, LogstashUiPluginStart } from './types';
import { defineRoutes } from './routes';

export class LogstashUiPlugin
  implements Plugin<LogstashUiPluginSetup, LogstashUiPluginStart>
{
  private readonly logger: Logger;

  constructor(initializerContext: PluginInitializerContext) {
    this.logger = initializerContext.logger.get();
  }

  setup(core: CoreSetup) {
    core.capabilities.registerProvider(() => ({
      logstashUi: { show: true, save: true },
    }));

    // create a router and register routes defined in routes/index.ts
    const router = core.http.createRouter();
    defineRoutes(router);

    this.logger.debug('logstashUi: Setup complete');
  }

  public start(core: CoreStart) {
    this.logger.debug('logstashUi: Started');
    return {};
  }

  public stop() {}
}
