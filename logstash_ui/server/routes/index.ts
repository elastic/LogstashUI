import type { IRouter } from '@kbn/core/server';

export function defineRoutes(router: IRouter) {
  router.get(
    {
      path: '/api/logstash_ui/configs',
      validate: false,
    },
    async (context, req, res) => {
      const esClient = (await context.core).elasticsearch.client;

      try {
        // query the .logstash index
        const result = await esClient.asCurrentUser.search({
          index: '.logstash',
          size: 1000
        });

        return res.ok({
          body: result.hits.hits.map((h) => h._source),
        });
      } catch (e) {
        return res.customError({
          statusCode: 500,
          body: { message: e.message },
        });
      }
    }
  );
}
