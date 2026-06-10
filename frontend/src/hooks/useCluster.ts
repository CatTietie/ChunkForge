import { useState, useEffect, useCallback } from 'react';
import type { ClusterStatus, FileMeta } from '../types';
import { fetchClusterStatus, listFiles } from '../api/client';

export function useCluster() {
  const [cluster, setCluster] = useState<ClusterStatus | null>(null);
  const [files, setFiles] = useState<FileMeta[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const [status, fileList] = await Promise.all([
        fetchClusterStatus(),
        listFiles(),
      ]);
      setCluster(status);
      setFiles(fileList);
    } catch (e) {
      console.error('Failed to fetch cluster status:', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 3000);
    return () => clearInterval(interval);
  }, [refresh]);

  return { cluster, files, loading, refresh };
}
