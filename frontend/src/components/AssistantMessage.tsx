'use client';

import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AssistantMessageData, ReasoningStep, Source } from '@/types';
import DataCardGrid from './DataCardGrid';
import CollapsibleSteps from './CollapsibleSteps';

interface AssistantMessageProps {
  data: AssistantMessageData;
  reasoningSteps?: ReasoningStep[];
}

function SourceItem({ source }: { source: Source }) {
  const [expanded, setExpanded] = useState(false);
  const domainLabel = source.domain === 'law' ? '법령' : '가이드';
  const domainColor = source.domain === 'law'
    ? 'bg-blue-50 text-blue-600 border-blue-200'
    : 'bg-emerald-50 text-emerald-600 border-emerald-200';

  return (
    <li className="text-sm">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full text-left flex items-start gap-2 py-1.5 px-2 rounded-lg hover:bg-slate-50 transition-colors"
      >
        <span className="material-symbols-outlined text-slate-400 text-base mt-0.5 shrink-0"
              style={{ fontSize: '16px' }}>
          {expanded ? 'expand_more' : 'chevron_right'}
        </span>
        <span className={`px-1.5 py-0.5 rounded text-[10px] font-semibold border shrink-0 mt-0.5 ${domainColor}`}>
          {domainLabel}
        </span>
        <span className="text-slate-700">
          <span className="font-medium">{source.title}</span>
          {source.section && source.section !== 'N/A' && (
            <span className="text-slate-400 ml-1.5">{source.section}</span>
          )}
        </span>
        {source.similarity && (
          <span className="ml-auto text-[10px] text-slate-400 shrink-0 mt-0.5">
            유사도 {source.similarity}
          </span>
        )}
      </button>
      {expanded && source.preview && (
        <div className="ml-8 mr-2 mt-1 mb-2 p-3 bg-slate-50 rounded-lg border border-slate-100 text-xs text-slate-600 leading-relaxed whitespace-pre-wrap">
          {source.preview}
        </div>
      )}
    </li>
  );
}

export default function AssistantMessage({ data, reasoningSteps }: AssistantMessageProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[62rem] flex gap-4">
        <div className="size-8 rounded-lg bg-blue-50 flex items-center justify-center shrink-0 border border-blue-100">
          <span className="material-symbols-outlined text-primary text-lg">smart_toy</span>
        </div>
        <div className="space-y-4 min-w-0 flex-1">
          {reasoningSteps && reasoningSteps.length > 0 && (
            <CollapsibleSteps steps={reasoningSteps} />
          )}
          <div className="bg-white border border-slate-200 p-5 rounded-2xl rounded-tl-none shadow-sm">
            {data.title && (
              <h3 className="font-semibold mb-3 text-slate-900">{data.title}</h3>
            )}
            <div className="prose prose-sm max-w-none prose-headings:text-slate-900 prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2 prose-p:text-slate-600 prose-p:leading-relaxed prose-p:my-2 prose-strong:text-slate-900 prose-ul:text-slate-600 prose-ol:text-slate-600 prose-li:my-0.5 prose-a:text-blue-600 prose-a:no-underline hover:prose-a:underline prose-code:text-blue-600 prose-code:bg-slate-100 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none prose-pre:bg-slate-50 prose-pre:border prose-pre:border-slate-200 prose-pre:rounded-lg prose-table:border-collapse prose-th:border prose-th:border-slate-200 prose-th:px-3 prose-th:py-1.5 prose-th:bg-slate-50 prose-td:border prose-td:border-slate-200 prose-td:px-3 prose-td:py-1.5 prose-hr:border-slate-200 mb-4">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.content}</ReactMarkdown>
            </div>
            {data.dataCards && data.dataCards.length > 0 && (
              <DataCardGrid cards={data.dataCards} />
            )}
            {data.sources && data.sources.length > 0 && (
              <details className="mt-4 pt-3 border-t border-slate-100">
                <summary className="cursor-pointer text-xs text-slate-500 flex items-center gap-1.5 select-none hover:text-slate-700 transition-colors list-none [&::-webkit-details-marker]:hidden">
                  <span className="material-symbols-outlined text-base" style={{ fontSize: '16px' }}>
                    menu_book
                  </span>
                  <span>참고 출처</span>
                  <span className="bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded-full text-[10px] font-medium">
                    {data.sources.length}
                  </span>
                </summary>
                <ul className="mt-2 space-y-0.5">
                  {data.sources.map((src, i) => (
                    <SourceItem key={`${src.title}-${src.section}-${i}`} source={src} />
                  ))}
                </ul>
              </details>
            )}
            {(data.source || data.processingTime) && (
              <div className="mt-4 pt-4 border-t border-slate-100 flex items-center gap-4 text-xs text-slate-400">

                {data.processingTime && (
                  <span className="flex items-center gap-1">
                    <span className="material-symbols-outlined text-sm">schedule</span>
                    {data.processingTime} Processing
                  </span>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
