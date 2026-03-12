'use client';

import { useState, useEffect, useRef } from 'react';
import { ReasoningStep } from '@/types';

interface CollapsibleStepsProps {
  steps: ReasoningStep[];
  isActive?: boolean;
}

export default function CollapsibleSteps({ steps, isActive = false }: CollapsibleStepsProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState(0);
  const hasAutoCollapsedRef = useRef(false);

  const completedCount = steps.filter((s) => s.status === 'completed').length;
  const hasInProgress = steps.some((s) => s.status === 'in_progress');
  const hasError = steps.some((s) => s.status === 'error');
  const allCompleted = steps.length > 0 && completedCount === steps.length && !isActive;

  // Auto-expand when first step arrives, auto-collapse when all done
  useEffect(() => {
    if (hasInProgress && !hasAutoCollapsedRef.current) {
      setIsExpanded(true);
    }
    if (allCompleted && !hasAutoCollapsedRef.current) {
      hasAutoCollapsedRef.current = true;
      setIsExpanded(false);
    }
  }, [hasInProgress, allCompleted]);

  // Measure content height for smooth transition
  useEffect(() => {
    if (contentRef.current) {
      setContentHeight(contentRef.current.scrollHeight);
    }
  }, [steps, isExpanded]);

  const summaryNames = steps.slice(0, 3).map((s) => s.name);
  const extraCount = steps.length - summaryNames.length;
  const summaryText = summaryNames.join(', ') + (extraCount > 0 ? ` +${extraCount} more` : '');

  function getStatusDot(status: ReasoningStep['status']) {
    switch (status) {
      case 'completed':
        return <span className="size-2 rounded-full bg-emerald-500 shrink-0" />;
      case 'in_progress':
        return <span className="size-2 rounded-full bg-primary animate-pulse shrink-0" />;
      case 'pending':
        return <span className="size-2 rounded-full bg-slate-600 shrink-0" />;
      default:
        return <span className="size-2 rounded-full bg-red-500 shrink-0" />;
    }
  }

  function getStatusLabel(status: ReasoningStep['status']) {
    switch (status) {
      case 'completed':
        return 'Completed';
      case 'in_progress':
        return 'In Progress';
      case 'pending':
        return 'Pending';
      default:
        return 'Error';
    }
  }

  if (steps.length === 0) return null;

  return (
    <div className="mb-3">
      {/* Collapsed summary / toggle bar */}
      <button
        type="button"
        onClick={() => setIsExpanded((prev) => !prev)}
        className="w-full flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-50 border border-slate-200 hover:bg-slate-100 transition-colors text-left group"
      >
        <span className="material-symbols-outlined text-base text-slate-400 transition-transform duration-200"
          style={{ transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)' }}
        >
          expand_more
        </span>

        {hasInProgress && (
          <span className="size-2 rounded-full bg-primary animate-pulse shrink-0" />
        )}
        {!hasInProgress && hasError && (
          <span className="size-2 rounded-full bg-red-500 shrink-0" />
        )}
        {!hasInProgress && !hasError && allCompleted && (
          <span className="size-2 rounded-full bg-emerald-500 shrink-0" />
        )}

        <span className="text-xs text-slate-500 truncate">
          <span className="text-slate-700 font-medium">
            {completedCount} of {steps.length} step{steps.length !== 1 ? 's' : ''} completed
          </span>
          {' '}&mdash; {summaryText}
        </span>
      </button>

      {/* Expandable content */}
      <div
        className="overflow-hidden transition-all duration-300 ease-in-out"
        style={{
          maxHeight: isExpanded ? `${contentHeight}px` : '0px',
          opacity: isExpanded ? 1 : 0,
        }}
      >
        <div ref={contentRef} className="pt-2 pl-2">
          <div className="border-l border-slate-200 ml-2 space-y-0">
            {steps.map((step, i) => (
              <div key={`${step.name}-${i}`} className="relative pl-5 py-1.5">
                {/* Dot on the timeline */}
                <div className="absolute left-[-3.5px] top-[10px]">
                  {getStatusDot(step.status)}
                </div>

                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <span className={`text-xs font-semibold block ${
                      step.status === 'completed' || step.status === 'in_progress'
                        ? 'text-slate-700'
                        : 'text-slate-400'
                    }`}>
                      {step.name}
                    </span>
                    {step.description && (
                      <span className="text-[11px] text-slate-400 leading-snug block mt-0.5">
                        {step.description}
                      </span>
                    )}
                  </div>
                  <span className={`text-[10px] whitespace-nowrap mt-0.5 ${
                    step.status === 'in_progress' ? 'text-blue-600' : 'text-slate-400'
                  }`}>
                    {getStatusLabel(step.status)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
