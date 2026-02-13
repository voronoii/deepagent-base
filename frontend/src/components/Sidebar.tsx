'use client';

const navItems = [
  { icon: 'dashboard', label: 'Dashboard', active: true },
  { icon: 'history', label: 'Activity Logs', active: false },
  { icon: 'database', label: 'Knowledge Base', active: false },
  { icon: 'settings', label: 'Settings', active: false },
];

interface SidebarProps {
  tokenUsed?: number;
  tokenTotal?: number;
}

export default function Sidebar({ tokenUsed = 1240, tokenTotal = 8000 }: SidebarProps) {
  const pct = Math.round((tokenUsed / tokenTotal) * 100);

  return (
    <aside className="w-64 border-r border-border-dark bg-bg-dark flex-col hidden lg:flex">
      <div className="p-6">
        <div className="flex items-center gap-3 text-primary mb-8">
          <span className="material-symbols-outlined text-3xl">account_balance</span>
          <h1 className="text-lg font-bold leading-tight tracking-tight text-white">InstiAgent</h1>
        </div>
        <nav className="space-y-1">
          {navItems.map((item) => (
            <a
              key={item.label}
              href="#"
              className={
                item.active
                  ? 'flex items-center gap-3 px-3 py-2 rounded-lg bg-primary/10 text-primary font-medium'
                  : 'flex items-center gap-3 px-3 py-2 rounded-lg text-slate-400 hover:bg-panel-dark transition-colors'
              }
            >
              <span className="material-symbols-outlined">{item.icon}</span>
              <span>{item.label}</span>
            </a>
          ))}
        </nav>
      </div>
      <div className="mt-auto p-4 border-t border-border-dark">
        <div className="bg-panel-dark p-4 rounded-xl">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-400">CONTEXT MEMORY</span>
            <span className="text-xs font-bold text-primary">{pct}%</span>
          </div>
          <div className="w-full bg-slate-700 rounded-full h-1.5 mb-3">
            <div
              className="bg-primary h-1.5 rounded-full transition-all"
              style={{ width: `${pct}%` }}
            />
          </div>
          <p className="text-[10px] text-slate-400 uppercase tracking-wider">
            {tokenUsed.toLocaleString()} / {tokenTotal.toLocaleString()} tokens
          </p>
        </div>
      </div>
    </aside>
  );
}
