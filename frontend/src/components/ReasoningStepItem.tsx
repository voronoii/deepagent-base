'use client';

import { ReasoningStep as ReasoningStepType } from '@/types';

interface ReasoningStepProps {
  step: ReasoningStepType;
  isLast: boolean;
}

export default function ReasoningStepItem({ step, isLast }: ReasoningStepProps) {
  const isCompleted = step.status === 'completed';
  const isInProgress = step.status === 'in_progress';

  return (
    <div className="relative pl-8">
      {/* Vertical line */}
      {!isLast && (
        <div className="absolute left-0 top-0 h-full w-[1px] bg-border-dark" />
      )}

      {/* Status dot */}
      {isCompleted ? (
        <div className="absolute -left-[4px] top-0 size-2 rounded-full bg-primary ring-4 ring-primary/20" />
      ) : (
        <div className="absolute -left-[4px] top-0 size-2 rounded-full bg-slate-600" />
      )}

      <div>
        <div className="flex items-center justify-between mb-1">
          <span
            className={`text-xs font-bold ${
              isCompleted || isInProgress ? 'text-white' : 'text-slate-400'
            }`}
          >
            {step.name}
          </span>
          <span className="text-[10px] text-slate-400">
            {isInProgress ? 'In Progress' : step.timestamp || ''}
          </span>
        </div>

        {step.description && (
          <p className="text-xs text-slate-400 leading-relaxed">{step.description}</p>
        )}

        {step.codeBlock && (
          <div className="mt-2 bg-panel-dark p-2 rounded border border-border-dark">
            <p className="text-[10px] font-mono text-slate-400">{step.codeBlock}</p>
          </div>
        )}

        {step.result && isCompleted && (
          <p className="text-[10px] mt-2 text-primary font-medium flex items-center gap-1">
            <span className="material-symbols-outlined text-[12px]">check_circle</span>
            {step.result}
          </p>
        )}

        {isInProgress && (
          <div className="flex gap-1 mt-2">
            <span className="size-1 bg-slate-400 rounded-full animate-bounce" />
            <span
              className="size-1 bg-slate-400 rounded-full animate-bounce"
              style={{ animationDelay: '0.2s' }}
            />
            <span
              className="size-1 bg-slate-400 rounded-full animate-bounce"
              style={{ animationDelay: '0.4s' }}
            />
          </div>
        )}
      </div>
    </div>
  );
}
