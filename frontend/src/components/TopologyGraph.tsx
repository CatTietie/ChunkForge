import { useEffect, useRef } from 'react';
import * as d3 from 'd3';
import type { NodeInfo } from '../types';

interface Props {
  nodes: NodeInfo[];
  onCrash: (nodeId: string) => void;
  onRecover: (nodeId: string) => void;
}

const STATUS_COLORS: Record<string, string> = {
  online: '#22c55e',
  offline: '#6b7280',
  crashed: '#ef4444',
  draining: '#f59e0b',
};

export function TopologyGraph({ nodes, onCrash, onRecover }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || nodes.length === 0) return;

    const width = 600;
    const height = 400;
    const svg = d3.select(svgRef.current);
    svg.selectAll('*').remove();

    svg.attr('viewBox', `0 0 ${width} ${height}`);

    // Coordinator at center
    const center = { id: 'coordinator', x: width / 2, y: height / 2 };

    // Layout nodes in a circle
    const angleStep = (2 * Math.PI) / nodes.length;
    const radius = 150;
    const nodePositions = nodes.map((n, i) => ({
      ...n,
      x: width / 2 + radius * Math.cos(angleStep * i - Math.PI / 2),
      y: height / 2 + radius * Math.sin(angleStep * i - Math.PI / 2),
    }));

    // Draw links
    svg.selectAll('line.link')
      .data(nodePositions)
      .join('line')
      .attr('class', 'link')
      .attr('x1', center.x)
      .attr('y1', center.y)
      .attr('x2', (d) => d.x)
      .attr('y2', (d) => d.y)
      .attr('stroke', (d) => d.status === 'online' ? '#94a3b8' : '#ef4444')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', (d) => d.status === 'crashed' ? '4,4' : 'none')
      .attr('opacity', 0.6);

    // Draw coordinator
    svg.append('circle')
      .attr('cx', center.x)
      .attr('cy', center.y)
      .attr('r', 25)
      .attr('fill', '#3b82f6')
      .attr('stroke', '#1d4ed8')
      .attr('stroke-width', 2);

    svg.append('text')
      .attr('x', center.x)
      .attr('y', center.y + 4)
      .attr('text-anchor', 'middle')
      .attr('fill', 'white')
      .attr('font-size', '10px')
      .attr('font-weight', 'bold')
      .text('COORD');

    // Draw nodes
    const nodeGroups = svg.selectAll('g.node')
      .data(nodePositions)
      .join('g')
      .attr('class', 'node')
      .attr('transform', (d) => `translate(${d.x}, ${d.y})`)
      .style('cursor', 'pointer');

    nodeGroups.append('circle')
      .attr('r', 20)
      .attr('fill', (d) => STATUS_COLORS[d.status] || '#6b7280')
      .attr('stroke', '#1f2937')
      .attr('stroke-width', 2);

    nodeGroups.append('text')
      .attr('y', 4)
      .attr('text-anchor', 'middle')
      .attr('fill', 'white')
      .attr('font-size', '9px')
      .attr('font-weight', 'bold')
      .text((d) => d.node_id.replace('node-', 'N'));

    // Shard count badge
    nodeGroups.append('text')
      .attr('y', 35)
      .attr('text-anchor', 'middle')
      .attr('fill', '#374151')
      .attr('font-size', '10px')
      .text((d) => `${d.shard_count} shards`);

    // Click handler
    nodeGroups.on('click', (_event, d) => {
      if (d.status === 'online') {
        onCrash(d.node_id);
      } else if (d.status === 'crashed') {
        onRecover(d.node_id);
      }
    });

  }, [nodes, onCrash, onRecover]);

  return (
    <div style={{ border: '1px solid #e5e7eb', borderRadius: 8, padding: 8 }}>
      <h3 style={{ margin: '0 0 8px', fontSize: 14 }}>
        集群拓扑 <span style={{ fontSize: 11, color: '#6b7280' }}>(点击节点切换状态)</span>
      </h3>
      <svg ref={svgRef} style={{ width: '100%', height: 400 }} />
      <div style={{ display: 'flex', gap: 16, fontSize: 11, marginTop: 4 }}>
        {Object.entries(STATUS_COLORS).map(([status, color]) => (
          <span key={status} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: '50%', background: color, display: 'inline-block' }} />
            {status}
          </span>
        ))}
      </div>
    </div>
  );
}
