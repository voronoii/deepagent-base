'use client';

import { DataCard } from '@/types';

interface DataCardGridProps {
  cards: DataCard[];
}

export default function DataCardGrid({ cards }: DataCardGridProps) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {cards.map((card, i) => (
        <div
          key={i}
          className="bg-slate-50 p-3 rounded-lg border border-slate-200"
        >
          <p className="text-[10px] text-slate-500 uppercase font-bold">{card.label}</p>
          <p className="text-lg font-bold text-blue-600">{card.value}</p>
        </div>
      ))}
    </div>
  );
}
