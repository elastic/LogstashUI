import type { NavigationPublicPluginStart } from '@kbn/navigation-plugin/public';

export interface LogstashUiPluginSetup {
  getGreeting: () => string;
}
// eslint-disable-next-line @typescript-eslint/no-empty-interface
export interface LogstashUiPluginStart {}

export interface AppPluginStartDependencies {
  navigation: NavigationPublicPluginStart;
}
