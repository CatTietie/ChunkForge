import type { ClusterStatus, FileMeta, NodeInfo } from '../types';

const BASE = '';

export async function fetchClusterStatus(): Promise<ClusterStatus> {
  const resp = await fetch(`${BASE}/cluster/status`);
  return resp.json();
}

export async function addNode(node: Partial<NodeInfo>): Promise<void> {
  await fetch(`${BASE}/cluster/nodes`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(node),
  });
}

export async function crashNode(nodeId: string): Promise<void> {
  await fetch(`${BASE}/cluster/nodes/${nodeId}/crash`, { method: 'POST' });
}

export async function recoverNode(nodeId: string): Promise<void> {
  await fetch(`${BASE}/cluster/nodes/${nodeId}/recover`, { method: 'POST' });
}

export async function removeNode(nodeId: string): Promise<void> {
  await fetch(`${BASE}/cluster/nodes/${nodeId}`, { method: 'DELETE' });
}

export async function uploadFile(file: File): Promise<FileMeta> {
  const form = new FormData();
  form.append('file', file);
  const resp = await fetch(`${BASE}/files/upload`, { method: 'POST', body: form });
  return resp.json();
}

export async function downloadFile(fileId: string, filename: string): Promise<void> {
  const resp = await fetch(`${BASE}/files/${fileId}/download`);
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export async function deleteFile(fileId: string): Promise<void> {
  await fetch(`${BASE}/files/${fileId}`, { method: 'DELETE' });
}

export async function listFiles(): Promise<FileMeta[]> {
  const resp = await fetch(`${BASE}/files`);
  const data = await resp.json();
  return data.files;
}

export async function triggerRebalance(): Promise<{ triggered: boolean; state: string }> {
  const resp = await fetch(`${BASE}/cluster/rebalance`, { method: 'POST' });
  return resp.json();
}

export async function getRebalanceStatus(): Promise<Record<string, unknown>> {
  const resp = await fetch(`${BASE}/cluster/rebalance`);
  return resp.json();
}
