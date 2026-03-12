'use client';

interface MetadataItem {
  label: string;
  value: string;
  valueClassName?: string;
}

const defaultMetadata: MetadataItem[] = [
  { label: 'Processing Engine', value: 'Neural-7B-v4', valueClassName: 'text-slate-600 font-mono' },
  { label: 'Security Clearance', value: 'L-3 Institutional', valueClassName: 'text-green-600 font-bold' },
  { label: 'Latency', value: '124ms', valueClassName: 'text-slate-600' },
];

interface MetadataPanelProps {
  items?: MetadataItem[];
}

export default function MetadataPanel({ items = defaultMetadata }: MetadataPanelProps) {
  return (
    <div className="mt-12">
      <h2 className="text-xs font-bold uppercase tracking-widest text-slate-400 mb-4">Metadata</h2>
      <div className="space-y-3">
        {items.map((item, i) => (
          <div key={i} className="flex justify-between text-xs">
            <span className="text-slate-400">{item.label}</span>
            <span className={item.valueClassName || 'text-slate-600'}>{item.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
