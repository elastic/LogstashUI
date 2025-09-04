import type { PluginInitializerContext } from '@kbn/core/server';

//  This exports static code and TypeScript types,
//  as well as, Kibana Platform `plugin()` initializer.

export async function plugin(initializerContext: PluginInitializerContext) {
  const { LogstashUiPlugin } = await import('./plugin');
  return new LogstashUiPlugin(initializerContext);
}

export type { LogstashUiPluginSetup, LogstashUiPluginStart } from './types';