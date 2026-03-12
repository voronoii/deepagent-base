'use client';

import { useState, useRef, useEffect, KeyboardEvent } from 'react';
import { TokenUsage } from '@/types';
import McpOverlay from './McpOverlay';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled?: boolean;
  tokenUsage: TokenUsage | null;
}

export default function ChatInput({ onSend, disabled = false, tokenUsage }: ChatInputProps) {
  const [value, setValue] = useState('');
  const [mcpOpen, setMcpOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [value]);

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue('');
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  const usagePercent = tokenUsage
    ? Math.min((tokenUsage.promptTokens / tokenUsage.maxContextTokens) * 100, 100)
    : 0;

  const usageColor =
    usagePercent > 90 ? 'text-red-400' :
    usagePercent > 70 ? 'text-amber-400' :
    'text-slate-400';

  const barColor =
    usagePercent > 90 ? 'bg-red-400' :
    usagePercent > 70 ? 'bg-amber-400' :
    'bg-primary';

  return (
    <div className="absolute bottom-0 left-0 right-0 p-6 bg-gradient-to-t from-slate-50 via-slate-50 to-transparent">
      <div className="max-w-4xl mx-auto relative">
        <div className="flex items-end gap-2 bg-white border border-slate-200 rounded-xl p-2 pr-3 shadow-lg">
          <button className="p-2 text-slate-400 hover:text-blue-600 transition-colors">
            <span className="material-symbols-outlined">attach_file</span>
          </button>
          <textarea
            ref={textareaRef}
            className="w-full bg-transparent border-none focus:ring-0 focus:outline-none text-sm py-2 px-2 resize-none text-slate-900 placeholder-slate-400"
            placeholder="Type a follow-up or a new command..."
            rows={1}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
          />
          <button
            onClick={handleSubmit}
            disabled={disabled || !value.trim()}
            className="bg-blue-600 text-white px-4 py-2 rounded-lg font-semibold text-sm flex items-center gap-2 hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <span>Send</span>
            <span className="material-symbols-outlined text-sm">send</span>
          </button>
        </div>

        {/* Token usage indicator */}
        <div className="flex items-center gap-3 mt-2 px-1">
          {/* MCP button */}
          <div className="relative">
            <McpOverlay isOpen={mcpOpen} onClose={() => setMcpOpen(false)} />
            <button
              onClick={() => setMcpOpen((p) => !p)}
              title="MCP Connections"
              className={`flex items-center gap-1 px-1.5 py-0.5 rounded-md text-[11px] font-medium transition-colors border ${
                mcpOpen
                  ? 'text-blue-600 bg-blue-50 border-blue-200'
                  : 'text-slate-400 bg-slate-50 border-slate-200 hover:text-blue-600 hover:bg-blue-50 hover:border-blue-200'
              }`}
            >
              <span className="material-symbols-outlined text-sm">hub</span>
              <span>MCP</span>
            </button>
          </div>

          <div className="flex items-center gap-1.5">
            <span className={`material-symbols-outlined text-xs ${usageColor}`}>token</span>
            <span className={`text-[11px] font-mono ${usageColor}`}>
              {tokenUsage
                ? `${tokenUsage.promptTokens.toLocaleString()} / ${tokenUsage.maxContextTokens.toLocaleString()}`
                : '— / —'
              }
            </span>
          </div>
          <div className="w-24 h-1.5 bg-slate-200 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ease-out ${barColor}`}
              style={{ width: `${usagePercent}%` }}
            />
          </div>
          <span className={`text-[11px] font-mono ${usageColor}`}>
            {tokenUsage ? `${usagePercent.toFixed(1)}%` : ''}
          </span>
        </div>
      </div>
    </div>
  );
}
