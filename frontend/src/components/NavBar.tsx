import type { AppView } from '../types';

interface NavBarProps {
  currentView: AppView;
  sessionId: string | null;
  onNavigate: (view: AppView) => void;
}

const NAV_ITEMS: { label: string; view: AppView }[] = [
  { label: 'Анализ', view: 'dashboard' },
  { label: 'Чат с Coach', view: 'chat' },
  { label: 'Plan Steps', view: 'plan' },
  { label: 'Приватность', view: 'privacy' },
];

export function NavBar({ currentView, sessionId, onNavigate }: NavBarProps) {
  const canNavigate = sessionId !== null && currentView !== 'upload' && currentView !== 'processing';

  return (
    <nav className="nav container">
      <button className="nav-logo" onClick={() => onNavigate('upload')} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
        <span className="nav-logo-mark">C</span>
        <span className="nav-wordmark">ClearMind</span>
      </button>

      {canNavigate && (
        <ul className="nav-links">
          {NAV_ITEMS.map(({ label, view }) => (
            <li key={view}>
              <button
                className={`nav-link${currentView === view ? ' active' : ''}`}
                onClick={() => onNavigate(view)}
              >
                {label}
              </button>
            </li>
          ))}
        </ul>
      )}

      {canNavigate && (
        <div className="nav-actions">
          <button className="btn btn-ghost btn-sm" onClick={() => onNavigate('privacy')}>
            🔒 Отчёт
          </button>
          <button className="btn btn-black btn-sm" onClick={() => onNavigate('upload')}>
            Новый файл
          </button>
        </div>
      )}
    </nav>
  );
}
