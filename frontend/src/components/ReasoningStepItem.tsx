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
        <div className="absolute left-0 top-0 h-full w-[1px] bg-slate-200" />
      )}

      {/* Status dot */}
      {isCompleted ? (
        <div className="absolute -left-[4px] top-0 size-2 rounded-full bg-blue-600 ring-4 ring-blue-100" />
      ) : (
        <div className="absolute -left-[4px] top-0 size-2 rounded-full bg-slate-300" />
      )}

      <div>
        <div className="flex items-center justify-between mb-1">
          <span
            className={`text-xs font-bold ${
              isCompleted || isInProgress ? 'text-slate-800' : 'text-slate-400'
            }`}
          >
            {step.name}
          </span>
          <span className="text-[10px] text-slate-400">
            {isInProgress ? 'In Progress' : step.timestamp || ''}
          </span>
        </div>

        {step.description && (
          <p className="text-xs text-slate-500 leading-relaxed">{step.description}</p>
        )}

        {step.codeBlock && (
          <div className="mt-2 bg-slate-50 p-2 rounded border border-slate-200">
            <p className="text-[10px] text-slate-600 font-mono">{step.codeBlock}</p>
          </div>
        )}

        {step.result && isCompleted && (
          <p className="text-[10px] mt-2 text-blue-600 font-medium flex items-center gap-1">
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
