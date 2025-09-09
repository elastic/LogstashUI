import { IRouter } from '@kbn/core/server';

export function defineRoutes(router: IRouter) {
  router.get(
    {
      path: '/api/logstash_ui/pipelines',
      validate: false,
      options: {
        authRequired: false,
        access: 'public'
      },
    },
    async (context, req, res) => {
      try {
        const esClient = context.core.elasticsearch.client.asCurrentUser;
        const result = await esClient.search({
          index: '.logstash',
          size: 50,
        });

        return res.ok({
          body: result.hits.hits.map((h: any) => h._source),
        });
      } catch (err: any) {
        return res.customError({
          statusCode: err.statusCode ?? 500,
          body: { message: err.message, meta: err.meta },
        });
      }
    }
  );
}
