'use client';

import { ReasoningStep } from '@/types';
import ReasoningStepItem from './ReasoningStepItem';

interface ReasoningPanelProps {
  steps: ReasoningStep[];
  isActive?: boolean;
}

export default function ReasoningPanel({ steps, isActive = false }: ReasoningPanelProps) {
  return (
    <aside className="w-80 border-l border-slate-200 bg-white overflow-y-auto hidden xl:block">
      <div className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-sm font-bold uppercase tracking-widest text-slate-400">
            Agent Reasoning
          </h2>
          {isActive && (
            <span className="flex h-2 w-2 rounded-full bg-green-500 animate-pulse" />
          )}
        </div>

        {/* Steps timeline */}
        {steps.length > 0 ? (
          <div className="space-y-6">
            {steps.map((step, i) => (
              <ReasoningStepItem
                key={`${step.name}-${i}`}
                step={step}
                isLast={i === steps.length - 1}
              />
            ))}
          </div>
        ) : (
          <div className="text-center py-12">
            <span className="material-symbols-outlined text-4xl text-slate-300 mb-3 block">
              psychology
            </span>
            <p className="text-xs text-slate-400">
              Reasoning steps will appear here when processing a query.
            </p>
          </div>
        )}

      </div>
    </aside>
  );
}
