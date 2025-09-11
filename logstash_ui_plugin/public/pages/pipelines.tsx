// public/pages/pipelines.tsx
import React, { useEffect, useState } from 'react';
import { EuiBasicTable, EuiTitle, EuiSpacer } from '@elastic/eui';
import type { CoreStart } from '@kbn/core/public';

interface PipelinesPageProps {
  http: CoreStart['http'];
  notifications: CoreStart['notifications'];
}

export const PipelinesPage: React.FC<PipelinesPageProps> = ({ http, notifications }) => {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    http
      .get('/api/logstash_ui/pipelines')
      .then((data) => setItems(data))
      .catch((err) => {
        notifications.toasts.addDanger(`Failed to load pipelines: ${err.message}`);
      })
      .finally(() => setLoading(false));
  }, [http, notifications]);

  const columns = [
    { field: 'pipeline.id', name: 'Pipeline ID' },
    { field: 'pipeline.workers', name: 'Workers' },
    { field: 'pipeline.batch.size', name: 'Batch Size' },
  ];

  return (
    <div>
      <EuiTitle size="l"><h2>Logstash Pipelines</h2></EuiTitle>
      <EuiSpacer />
      <EuiBasicTable
        items={items}
        columns={columns}
        loading={loading}
        rowHeader="pipeline.id"
      />
    </div>
  );
};
