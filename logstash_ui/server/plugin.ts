import type {
  PluginInitializerContext,
  CoreSetup,
  CoreStart,
  Plugin,
  Logger,
} from '@kbn/core/server';

import type { LogstashUiPluginSetup, LogstashUiPluginStart } from './types';
import { defineRoutes } from './routes';

export class LogstashUiPlugin implements Plugin<LogstashUiPluginSetup, LogstashUiPluginStart> {
  private readonly logger: Logger;

  constructor(initializerContext: PluginInitializerContext) {
    this.logger = initializerContext.logger.get();
  }

  public setup(core: CoreSetup) {
    this.logger.debug('logstashUI: Setup');
    const router = core.http.createRouter();

    // Register server side APIs
    defineRoutes(router);

    return {};
  }

  public start(core: CoreStart) {
    this.logger.debug('logstashUI: Started');
    return {};
  }

  public stop() {}
}
