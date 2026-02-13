'use client';

export default function TopNav() {
  return (
    <header className="h-16 border-b border-border-dark flex items-center justify-between px-8 bg-bg-dark z-10">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-slate-400">Workspaces</span>
        <span className="text-slate-400">/</span>
        <span className="font-medium text-white">Dept. of Finance Records</span>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm">
            search
          </span>
          <input
            className="bg-panel-dark border-none rounded-lg pl-9 pr-4 py-1.5 text-sm w-64 focus:ring-1 focus:ring-primary focus:outline-none text-slate-100 placeholder-slate-400"
            placeholder="Search insights..."
            type="text"
          />
        </div>
        <button className="flex items-center justify-center size-8 rounded-full bg-panel-dark text-slate-300 hover:text-white transition-colors">
          <span className="material-symbols-outlined text-xl">notifications</span>
        </button>
        <div className="size-8 rounded-full bg-primary/20 flex items-center justify-center border border-primary/30">
          <span className="text-xs font-bold text-primary">JD</span>
        </div>
      </div>
    </header>
  );
}
