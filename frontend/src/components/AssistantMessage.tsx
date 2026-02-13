'use client';

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { AssistantMessageData, ReasoningStep } from '@/types';
import DataCardGrid from './DataCardGrid';
import CollapsibleSteps from './CollapsibleSteps';

interface AssistantMessageProps {
  data: AssistantMessageData;
  reasoningSteps?: ReasoningStep[];
}

export default function AssistantMessage({ data, reasoningSteps }: AssistantMessageProps) {
  return (
    <div className="flex justify-start">
      <div className="max-w-[62rem] flex gap-4">
        <div className="size-8 rounded-lg bg-primary/10 flex items-center justify-center shrink-0 border border-primary/20">
          <span className="material-symbols-outlined text-primary text-lg">smart_toy</span>
        </div>
        <div className="space-y-4 min-w-0 flex-1">
          {reasoningSteps && reasoningSteps.length > 0 && (
            <CollapsibleSteps steps={reasoningSteps} />
          )}
          <div className="bg-panel-dark border border-border-dark p-5 rounded-2xl rounded-tl-none shadow-sm">
            {data.title && (
              <h3 className="font-semibold mb-3 text-white">{data.title}</h3>
            )}
            <div className="prose prose-invert prose-sm max-w-none
              prose-headings:text-white prose-headings:font-semibold prose-headings:mt-4 prose-headings:mb-2
              prose-p:text-slate-300 prose-p:leading-relaxed prose-p:my-2
              prose-strong:text-white
              prose-ul:text-slate-300 prose-ol:text-slate-300
              prose-li:my-0.5
              prose-a:text-primary prose-a:no-underline hover:prose-a:underline
              prose-code:text-primary prose-code:bg-slate-800/60 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:before:content-none prose-code:after:content-none
              prose-pre:bg-slate-900 prose-pre:border prose-pre:border-border-dark prose-pre:rounded-lg
              prose-table:border-collapse prose-th:border prose-th:border-border-dark prose-th:px-3 prose-th:py-1.5 prose-th:bg-slate-800/40 prose-td:border prose-td:border-border-dark prose-td:px-3 prose-td:py-1.5
              prose-hr:border-border-dark
              mb-4">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{data.content}</ReactMarkdown>
            </div>
            {data.dataCards && data.dataCards.length > 0 && (
              <DataCardGrid cards={data.dataCards} />
            )}
            {(data.source || data.processingTime) && (
              <div className="mt-4 pt-4 border-t border-slate-800 flex items-center gap-4 text-xs text-slate-500">
                {data.source && (
                  <span className="flex items-center gap-1">
                    <span className="material-symbols-outlined text-sm">verified</span>
                    Verified Source: {data.source}
                  </span>
                )}
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
