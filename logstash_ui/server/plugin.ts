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

setup(core: CoreSetup) {
  core.capabilities.registerProvider(() => ({
    logstashUi: {
      show: true,
      save: true,
    },
  }));

  core.http.createRouter().get(
    {
      path: '/api/logstash_ui/pipelines',
      validate: false,
      options: {
        tags: ['access:logstashUi'],
      },
    },
    async (context, req, res) => {
      const esClient = context.core.elasticsearch.client.asCurrentUser;
      const result = await esClient.search({ index: '.logstash', size: 50 });
      return res.ok({ body: result.hits.hits.map(h => h._source) });
    }
  );
}

  public start(core: CoreStart) {
    this.logger.debug('logstashUi: Started');
    return {};
  }

  public stop() {}
}