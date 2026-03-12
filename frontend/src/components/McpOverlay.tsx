'use client';

import { useState, useEffect, useRef } from 'react';

interface McpTool {
  name: string;
  description: string;
}

interface McpServer {
  name: string;
  description: string;
  status: 'online' | 'offline' | 'error' | 'disabled';
  transport: string;
  url: string;
  latency_ms: number | null;
  tools: McpTool[];
  error: string | null;
  enabled: boolean;
}

interface McpHealthResponse {
  summary: {
    online: number;
    total_enabled: number;
    total: number;
  };
  servers: McpServer[];
  timestamp: string;
}

interface McpOverlayProps {
  isOpen: boolean;
  onClose: () => void;
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

function StatusBadge({ status }: { status: McpServer['status'] }) {
  const styles: Record<McpServer['status'], string> = {
    online: 'bg-green-100 text-green-700',
    offline: 'bg-red-100 text-red-700',
    error: 'bg-red-100 text-red-700',
    disabled: 'bg-slate-100 text-slate-500',
  };
  return (
    <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded-full uppercase tracking-wide ${styles[status]}`}>
      {status}
    </span>
  );
}

function ServerRow({ server }: { server: McpServer }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="border border-slate-100 rounded-lg p-3 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-semibold text-slate-800">{server.name}</span>
        <div className="flex items-center gap-2 flex-shrink-0">
          {server.latency_ms !== null && server.status === 'online' && (
            <span className="text-[10px] font-mono text-slate-400">{server.latency_ms}ms</span>
          )}
          <StatusBadge status={server.status} />
        </div>
      </div>
      {server.description && (
        <p className="text-[11px] text-slate-500 leading-relaxed">{server.description}</p>
      )}
      {server.error && (
        <p className="text-[11px] text-red-500 leading-relaxed">{server.error}</p>
      )}
      {server.tools.length > 0 && (
        <div>
          <button
            onClick={() => setExpanded((p) => !p)}
            className="flex items-center gap-1 text-[11px] text-slate-500 hover:text-blue-600 transition-colors"
          >
            <span className="material-symbols-outlined text-xs">
              {expanded ? 'expand_less' : 'expand_more'}
            </span>
            {server.tools.length} tool{server.tools.length !== 1 ? 's' : ''}
          </button>
          {expanded && (
            <ul className="mt-1.5 space-y-1 pl-2 border-l border-slate-200">
              {server.tools.map((tool) => (
                <li key={tool.name} className="text-[11px] text-slate-600">
                  <span className="font-mono font-medium">{tool.name}</span>
                  {tool.description && (
                    <span className="text-slate-400"> — {tool.description}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export default function McpOverlay({ isOpen, onClose }: McpOverlayProps) {
  const [data, setData] = useState<McpHealthResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/api/mcp/health`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<McpHealthResponse>;
      })
      .then((json) => {
        setData(json);
        setLoading(false);
      })
      .catch((err: Error) => {
        setError(err.message || 'Failed to fetch MCP status');
        setLoading(false);
      });
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose();
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen) return;
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKey);
    return () => document.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  return (
    <div
      className={`absolute bottom-full left-0 mb-2 z-50 transition-all duration-200 ${
        isOpen ? 'opacity-100 translate-y-0 pointer-events-auto' : 'opacity-0 translate-y-2 pointer-events-none'
      }`}
    >
      <div
        ref={panelRef}
        className="w-80 bg-white border border-slate-200 rounded-xl shadow-xl overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-sm text-blue-600">hub</span>
            <span className="text-sm font-semibold text-slate-800">MCP Connections</span>
          </div>
          <div className="flex items-center gap-2">
            {data && (
              <>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-green-100 text-green-700">
                  {data.summary.online} online
                </span>
                <span className="text-[10px] font-semibold px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500">
                  {data.summary.total} total
                </span>
              </>
            )}
            <button
              onClick={onClose}
              className="p-0.5 text-slate-400 hover:text-slate-600 transition-colors rounded"
            >
              <span className="material-symbols-outlined text-base">close</span>
            </button>
          </div>
        </div>

        {/* Body */}
        <div className="p-3 max-h-72 overflow-y-auto">
          {loading && (
            <div className="flex items-center justify-center py-8 gap-2 text-slate-400">
              <span className="material-symbols-outlined text-sm animate-spin">progress_activity</span>
              <span className="text-xs">Fetching status...</span>
            </div>
          )}
          {!loading && error && (
            <div className="flex items-center gap-2 py-4 text-red-500">
              <span className="material-symbols-outlined text-sm">error</span>
              <span className="text-xs">{error}</span>
            </div>
          )}
          {!loading && data && data.servers.length === 0 && (
            <p className="text-xs text-slate-400 text-center py-6">No MCP servers configured.</p>
          )}
          {!loading && data && data.servers.length > 0 && (
            <div className="space-y-2">
              {data.servers.map((server) => (
                <ServerRow key={server.name} server={server} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
