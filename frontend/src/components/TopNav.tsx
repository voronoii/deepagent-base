'use client';

export default function TopNav() {
  return (
    <header className="h-16 border-b border-slate-200 bg-white flex items-center justify-between px-8 z-10">
      <div className="flex items-center gap-2 text-sm">
        <span className="text-slate-400">Workspaces</span>
        <span className="text-slate-400">/</span>
        <span className="font-medium text-slate-900">Dept. of Finance Records</span>
      </div>
      <div className="flex items-center gap-4">
        <div className="relative">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 text-sm">
            search
          </span>
          <input
            className="bg-slate-50 border border-slate-200 rounded-lg pl-9 pr-4 py-1.5 text-sm w-64 focus:ring-1 focus:ring-blue-500 focus:border-blue-500 focus:outline-none text-slate-900 placeholder-slate-400"
            placeholder="Search insights..."
            type="text"
          />
        </div>
        <button className="flex items-center justify-center size-8 rounded-full bg-slate-50 text-slate-500 hover:text-slate-700 hover:bg-slate-100 transition-colors">
          <span className="material-symbols-outlined text-xl">notifications</span>
        </button>
        <div className="size-8 rounded-full bg-blue-50 flex items-center justify-center border border-blue-200">
          <span className="text-xs font-bold text-blue-600">JD</span>
        </div>
      </div>
    </header>
  );
}
