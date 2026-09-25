import { useState, useEffect } from 'react';
import { DashboardView } from './views/DashboardView';
import { NoticeInput } from './views/NoticeInput';
import { NoticeResultsView } from './views/NoticeResultsView';
import { ReviewCenterView } from './views/ReviewCenterView';
import type { NoticeResult } from './types';
import { useQuery } from '@tanstack/react-query';

const fetchNotices = async (): Promise<NoticeResult[]> => {
  // Placeholder API call
  // return fetch('/api/notices').then(res => res.json());
  return [];
};

function App() {
  const [currentView, setCurrentView] = useState<'dashboard' | 'input' | 'review' | 'result'>('dashboard');
  const [selectedNotice] = useState<NoticeResult | null>(null);

  const { data: notices, isLoading, isError, error } = useQuery({
    queryKey: ['notices'],
    queryFn: fetchNotices,
  });

  // Handle simple hash routing
  useEffect(() => {
    const handleHashChange = () => {
      const hash = window.location.hash.replace('#', '');
      if (hash === 'input') setCurrentView('input');
      else if (hash === 'review') setCurrentView('review');
      else if (hash === 'dashboard' || !hash) setCurrentView('dashboard');
    };
    
    window.addEventListener('hashchange', handleHashChange);
    handleHashChange();
    return () => window.removeEventListener('hashchange', handleHashChange);
  }, []);

  return (
    <div className="min-h-screen flex flex-col bg-zinc-950 text-zinc-100 font-sans">
      <header className="border-b border-zinc-800 bg-zinc-900 sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <h1 className="font-mono font-bold tracking-tighter text-xl uppercase">FOMO-Zero</h1>
            <nav className="hidden sm:flex gap-4">
              <a href="#dashboard" className={`text-sm uppercase tracking-widest ${currentView === 'dashboard' ? 'text-zinc-100 font-bold' : 'text-zinc-500 hover:text-zinc-300'}`}>Dashboard</a>
              <a href="#input" className={`text-sm uppercase tracking-widest ${currentView === 'input' ? 'text-zinc-100 font-bold' : 'text-zinc-500 hover:text-zinc-300'}`}>Add Notice</a>
              <a href="#review" className={`text-sm uppercase tracking-widest ${currentView === 'review' ? 'text-zinc-100 font-bold' : 'text-zinc-500 hover:text-zinc-300'}`}>Review Center</a>
            </nav>
          </div>
        </div>
      </header>

      <main className="flex-grow p-4 sm:p-6 lg:p-8">
        {isLoading && (
          <div className="flex gap-4 max-w-7xl mx-auto">
            <div className="w-1/3 h-96 bg-zinc-800 animate-pulse border border-zinc-700"></div>
            <div className="w-1/3 h-96 bg-zinc-800 animate-pulse border border-zinc-700"></div>
            <div className="w-1/3 h-96 bg-zinc-800 animate-pulse border border-zinc-700"></div>
          </div>
        )}
        
        {isError && (
          <div className="border border-red-500/50 bg-red-950/20 p-4 max-w-4xl mx-auto">
            <h3 className="text-red-400 font-mono text-xs uppercase mb-2">API Error</h3>
            <p className="font-mono text-sm text-zinc-300">{error?.message || 'Failed to fetch notices.'}</p>
          </div>
        )}

        {!isLoading && !isError && (
          <>
            {currentView === 'dashboard' && <DashboardView notices={notices || []} />}
            {currentView === 'input' && <NoticeInput />}
            {currentView === 'review' && <ReviewCenterView data={notices || []} />}
            {currentView === 'result' && selectedNotice && <NoticeResultsView data={selectedNotice} />}
          </>
        )}
      </main>
    </div>
  );
}

export default App;
