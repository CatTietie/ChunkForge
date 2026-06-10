import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import type { FileMeta, NodeInfo } from '../types';

interface Props {
  files: FileMeta[];
  nodes: NodeInfo[];
}

export function ShardHeatmap({ files, nodes }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || files.length === 0 || nodes.length === 0) return;

    const margin = { top: 40, right: 20, bottom: 20, left: 120 };
    const cellSize = 30;
    const width = margin.left + nodes.length * cellSize + margin.right;
    const height = margin.top + files.length * cellSize + margin.bottom;

    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();
    svg.attr('viewBox', `0 0 ${width} ${height}`);

    // Build shard presence matrix
    const matrix: { fileIdx: number; nodeIdx: number; count: number; role: string }[] = [];
    files.forEach((file, fi) => {
      if (!file.shards) return;
      nodes.forEach((node, ni) => {
        const shardsOnNode = file.shards!.filter((s) => s.node_id === node.node_id);
        if (shardsOnNode.length > 0) {
          matrix.push({
            fileIdx: fi,
            nodeIdx: ni,
            count: shardsOnNode.length,
            role: shardsOnNode[0].role,
          });
        }
      });
    });

    const colorScale = d3.scaleOrdinal<string>()
      .domain(['data', 'parity'])
      .range(['#3b82f6', '#8b5cf6']);

    // Column headers (nodes)
    svg.selectAll('text.col-header')
      .data(nodes)
      .join('text')
      .attr('class', 'col-header')
      .attr('x', (_, i) => margin.left + i * cellSize + cellSize / 2)
      .attr('y', margin.top - 8)
      .attr('text-anchor', 'middle')
      .attr('font-size', '10px')
      .attr('fill', (d) => d.status === 'crashed' ? '#ef4444' : '#374151')
      .text((d) => d.node_id.replace('node-', 'N'));

    // Row headers (files)
    svg.selectAll('text.row-header')
      .data(files)
      .join('text')
      .attr('class', 'row-header')
      .attr('x', margin.left - 8)
      .attr('y', (_, i) => margin.top + i * cellSize + cellSize / 2 + 4)
      .attr('text-anchor', 'end')
      .attr('font-size', '10px')
      .attr('fill', '#374151')
      .text((d) => d.name.length > 14 ? d.name.slice(0, 14) + '…' : d.name);

    // Cells
    svg.selectAll('rect.cell')
      .data(matrix)
      .join('rect')
      .attr('class', 'cell')
      .attr('x', (d) => margin.left + d.nodeIdx * cellSize + 2)
      .attr('y', (d) => margin.top + d.fileIdx * cellSize + 2)
      .attr('width', cellSize - 4)
      .attr('height', cellSize - 4)
      .attr('rx', 4)
      .attr('fill', (d) => colorScale(d.role))
      .attr('opacity', 0.8);

    // Shard index labels in cells
    svg.selectAll('text.cell-label')
      .data(matrix)
      .join('text')
      .attr('class', 'cell-label')
      .attr('x', (d) => margin.left + d.nodeIdx * cellSize + cellSize / 2)
      .attr('y', (d) => margin.top + d.fileIdx * cellSize + cellSize / 2 + 4)
      .attr('text-anchor', 'middle')
      .attr('font-size', '9px')
      .attr('fill', 'white')
      .text((d) => d.count.toString());

  }, [files, nodes]);

  if (files.length === 0) {
    return <div style={{ color: '#6b7280', fontSize: 13 }}>上传文件后查看分片热力图</div>;
  }

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 8 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>分片分布热力图</h3>
      <svg ref={svgRef} style={{ width: '100%', maxHeight: 300 }} />
      <div style={{ display: 'flex', gap: 16, fontSize: 11, marginTop: 4 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#3b82f6', display: 'inline-block' }} />
          数据分片
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          <span style={{ width: 10, height: 10, borderRadius: 2, background: '#8b5cf6', display: 'inline-block' }} />
          校验分片
        </span>
      </div>
    </div>
  );
}
