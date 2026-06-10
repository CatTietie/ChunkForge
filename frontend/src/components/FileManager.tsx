import { useRef, useState } from 'react';
import type { FileMeta } from '../types';
import { uploadFile, downloadFile, deleteFile } from '../api/client';

interface Props {
  files: FileMeta[];
  onRefresh: () => void;
}

export function FileManager({ files, onRefresh }: Props) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);

  const handleUpload = async () => {
    const input = fileInput.current;
    if (!input?.files?.length) return;
    setUploading(true);
    try {
      await uploadFile(input.files[0]);
      input.value = '';
      onRefresh();
    } catch (e) {
      alert('上传失败: ' + e);
    } finally {
      setUploading(false);
    }
  };

  const handleDownload = (file: FileMeta) => {
    downloadFile(file.file_id, file.name);
  };

  const handleDelete = async (file: FileMeta) => {
    if (!confirm(`确认删除 ${file.name}？`)) return;
    await deleteFile(file.file_id);
    onRefresh();
  };

  const statusBadge = (status: string) => {
    const colors: Record<string, string> = {
      healthy: '#22c55e',
      degraded: '#f59e0b',
      repairing: '#3b82f6',
      lost: '#ef4444',
    };
    return (
      <span style={{
        padding: '1px 6px', borderRadius: 4, fontSize: 10,
        background: colors[status] || '#6b7280', color: 'white',
      }}>
        {status}
      </span>
    );
  };

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 8 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>文件管理</h3>
      <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
        <input ref={fileInput} type="file" style={{ fontSize: 12 }} />
        <button onClick={handleUpload} disabled={uploading} style={{ fontSize: 12 }}>
          {uploading ? '上传中...' : '上传'}
        </button>
      </div>
      <table style={{ width: '100%', fontSize: 12, borderCollapse: 'collapse' }}>
        <thead>
          <tr style={{ borderBottom: '1px solid #e5e7eb' }}>
            <th style={{ textAlign: 'left', padding: 4 }}>文件名</th>
            <th style={{ textAlign: 'right', padding: 4 }}>大小</th>
            <th style={{ textAlign: 'center', padding: 4 }}>状态</th>
            <th style={{ textAlign: 'center', padding: 4 }}>操作</th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <tr key={f.file_id} style={{ borderBottom: '1px solid #f3f4f6' }}>
              <td style={{ padding: 4 }}>{f.name}</td>
              <td style={{ padding: 4, textAlign: 'right' }}>{(f.size / 1024).toFixed(1)} KB</td>
              <td style={{ padding: 4, textAlign: 'center' }}>{statusBadge(f.status)}</td>
              <td style={{ padding: 4, textAlign: 'center' }}>
                <button onClick={() => handleDownload(f)} style={{ fontSize: 11, marginRight: 4 }}>
                  下载
                </button>
                <button onClick={() => handleDelete(f)} style={{ fontSize: 11, color: '#ef4444' }}>
                  删除
                </button>
              </td>
            </tr>
          ))}
          {files.length === 0 && (
            <tr><td colSpan={4} style={{ padding: 8, color: '#6b7280', textAlign: 'center' }}>暂无文件</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
