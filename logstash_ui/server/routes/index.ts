import { IRouter } from '@kbn/core/server';

export function defineRoutes(router: IRouter) {
    router.get(
      {
        path: '/api/logstash_ui/pipelines',
        validate: false,
        options: {
          authRequired: false,   // ⬅ disables Kibana authz check for this route
        },
      },
      async (context, req, res) => {
        try {
          const esClient = context.core.elasticsearch.client.asCurrentUser;

          const result = await esClient.search({
            index: '.logstash',
            size: 50,
          });

          const pipelines = result.hits.hits.map((h: any) => h._source);
          return res.ok({ body: pipelines });
        } catch (err: any) {
          return res.customError({
            statusCode: 500,
            body: { message: err.message },
          });
        }
      }
    );

}
