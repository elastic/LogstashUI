import React, { useEffect, useState } from 'react';
import { EuiBasicTable } from '@elastic/eui';
import type { CoreStart } from '@kbn/core/public';

interface LogstashUiAppProps {
  basename: string;
  http: CoreStart['http'];
  notifications: CoreStart['notifications'];
}

export const LogstashUiApp = ({ http }: LogstashUiAppProps) => {
  const [items, setItems] = useState<any[]>([]);

  useEffect(() => {
    http.get('/api/logstash_ui/configs').then((data) => {
      setItems(data);
    });
  }, [http]);

  const columns = [
    {
      field: 'pipeline.id',
      name: 'Pipeline ID',
    },
    {
      field: 'pipeline.workers',
      name: 'Workers',
    },
    {
      field: 'pipeline.batch.size',
      name: 'Batch Size',
    },
  ];

  return <EuiBasicTable items={items} columns={columns} />;
};
