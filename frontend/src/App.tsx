import { useCallback, useState } from 'react';
import { NavBar } from './components/NavBar';
import { UploadPage } from './pages/UploadPage';
import { DashboardPage } from './pages/DashboardPage';
import { ChatPage } from './pages/ChatPage';
import { PlanPage } from './pages/PlanPage';
import { PrivacyReportPage } from './pages/PrivacyReportPage';
import { tryParsePlan } from './api';
import type {
  AppState,
  AppView,
  ChatMessage,
  CoachPlan,
  PipelineStatusResponse,
  PrivacyReportResponse,
} from './types';

const INITIAL_STATE: AppState = {
  view: 'upload',
  sessionId: null,
  pipelineResult: null,
  plan: null,
  chatHistory: [],
  privacyReport: null,
};

function ProcessingOverlay({ message }: { message: string }) {
  return (
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(242,242,242,0.88)',
        backdropFilter: 'blur(6px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 999,
      }}
    >
      <div
        className="card"
        style={{ textAlign: 'center', padding: '48px 56px', maxWidth: 420 }}
      >
        <span className="spinner spinner-lg" style={{ display: 'block', margin: '0 auto 24px' }} />
        <p className="text-heading-sm" style={{ marginBottom: 8 }}>Анализируем данные</p>
        <p className="text-subheading">{message}</p>
      </div>
    </div>
  );
}

function ErrorBanner({ message, onDismiss }: { message: string; onDismiss: () => void }) {
  return (
    <div
      style={{
        position: 'fixed',
        bottom: 24,
        left: '50%',
        transform: 'translateX(-50%)',
        background: 'var(--color-white)',
        border: '1.5px solid var(--color-red)',
        borderRadius: 16,
        padding: '14px 20px',
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        zIndex: 1000,
        maxWidth: 480,
        width: 'calc(100vw - 48px)',
        boxShadow: 'var(--shadow-nav)',
      }}
    >
      <span style={{ fontSize: 20 }}>⚠️</span>
      <p className="text-body" style={{ flex: 1, fontSize: 14, color: 'var(--color-red)' }}>{message}</p>
      <button
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontSize: 18,
          color: 'var(--color-carbon)',
          opacity: 0.5,
          padding: 4,
          flexShrink: 0,
        }}
        onClick={onDismiss}
      >
        ✕
      </button>
    </div>
  );
}

export default function App() {
  const [state, setState] = useState<AppState>(INITIAL_STATE);
  const [processing, setProcessing] = useState(false);
  const [processingMessage, setProcessingMessage] = useState('');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  function navigate(view: AppView) {
    setState(s => ({ ...s, view }));
  }

  function handleSessionStarted(sessionId: string) {
    setState(s => ({ ...s, sessionId, view: 'upload' }));
    setProcessing(true);
    setProcessingMessage('Guard Agent проверяет данные…');
  }

  function handlePipelineComplete(sessionId: string, result: PipelineStatusResponse) {
    const plan = tryParsePlan(result.coach_message);
    setState(s => ({
      ...s,
      sessionId,
      pipelineResult: result,
      plan,
      view: 'dashboard',
    }));
    setProcessing(false);
    setProcessingMessage('');
  }

  function handleError(message: string) {
    setProcessing(false);
    setErrorMessage(message);
  }

  const handleMessagesUpdate = useCallback((messages: ChatMessage[]) => {
    setState(s => ({ ...s, chatHistory: messages }));
  }, []);

  function handlePlanUpdate(plan: CoachPlan) {
    setState(s => ({ ...s, plan }));
  }

  function handleReportLoaded(report: PrivacyReportResponse) {
    setState(s => ({ ...s, privacyReport: report }));
  }

  function handleSessionEnded() {
    setState(INITIAL_STATE);
  }

  const { view, sessionId, pipelineResult, plan, chatHistory, privacyReport } = state;

  return (
    <>
      <NavBar
        currentView={view}
        sessionId={sessionId}
        onNavigate={navigate}
      />

      {processing && <ProcessingOverlay message={processingMessage} />}

      {view === 'upload' && (
        <UploadPage
          onSessionStarted={handleSessionStarted}
          onPipelineComplete={handlePipelineComplete}
          onError={handleError}
        />
      )}

      {view === 'dashboard' && pipelineResult && (
        <DashboardPage
          pipelineResult={pipelineResult}
          onNavigate={navigate}
        />
      )}

      {view === 'chat' && sessionId && (
        <ChatPage
          sessionId={sessionId}
          initialMessages={chatHistory}
          onMessagesUpdate={handleMessagesUpdate}
          initialCoachMessage={pipelineResult?.coach_message ?? null}
        />
      )}

      {view === 'plan' && sessionId && (
        <PlanPage
          sessionId={sessionId}
          plan={plan}
          onPlanUpdate={handlePlanUpdate}
          coachMessage={pipelineResult?.coach_message ?? null}
          onGoToChat={() => navigate('chat')}
        />
      )}

      {view === 'privacy' && sessionId && (
        <PrivacyReportPage
          sessionId={sessionId}
          cachedReport={privacyReport}
          onReportLoaded={handleReportLoaded}
          onSessionEnded={handleSessionEnded}
        />
      )}

      {errorMessage && (
        <ErrorBanner message={errorMessage} onDismiss={() => setErrorMessage(null)} />
      )}
    </>
  );
}
