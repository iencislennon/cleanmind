import { ScoreGauge } from '../components/ScoreGauge';
import type { AppView, PipelineStatusResponse } from '../types';

interface DashboardPageProps {
  pipelineResult: PipelineStatusResponse;
  onNavigate: (view: AppView) => void;
}

function StatusBanner({ result }: { result: PipelineStatusResponse }) {
  if (result.status === 'error' || result.error_message) {
    return (
      <div
        style={{
          background: 'rgba(243,70,70,0.08)',
          border: '1.5px solid var(--color-red)',
          borderRadius: 16,
          padding: '16px 20px',
          marginBottom: 24,
        }}
      >
        <p className="text-body" style={{ color: 'var(--color-red)', fontWeight: 500 }}>
          ⚠️ {result.error_message ?? 'Конвейер завершился с ошибкой. Попробуй другой файл.'}
        </p>
      </div>
    );
  }
  return null;
}

export function DashboardPage({ pipelineResult, onNavigate }: DashboardPageProps) {
  const hasScore = pipelineResult.overload_score !== null;
  const score = pipelineResult.overload_score ?? 0;
  const hasMessage = Boolean(pipelineResult.coach_message);

  return (
    <div className="page">
      <div className="container" style={{ paddingTop: 48 }}>

        <StatusBanner result={pipelineResult} />

        {/* Score section */}
        <div className="card" style={{ marginBottom: 24 }}>
          <div
            className="flex items-center justify-between"
            style={{ gap: 40, flexWrap: 'wrap' }}
          >
            {/* Score gauge */}
            <div>
              <p className="text-caption" style={{ marginBottom: 24, letterSpacing: '0.5px', textTransform: 'uppercase' }}>
                Overload Score
              </p>
              {hasScore ? (
                <ScoreGauge score={score} />
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
                  <div
                    style={{
                      width: 220,
                      height: 220,
                      borderRadius: '50%',
                      border: '18px solid var(--color-hairline)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <p className="text-caption" style={{ textAlign: 'center', padding: 20 }}>
                      Оценка недоступна
                    </p>
                  </div>
                </div>
              )}
            </div>

            {/* Quick stats */}
            <div style={{ flex: 1, minWidth: 260 }}>
              <h2 className="text-heading-sm" style={{ marginBottom: 8 }}>
                {hasScore && score > 75 ? 'Нужно действовать' :
                 hasScore && score > 55 ? 'Есть над чем работать' :
                 hasScore && score > 30 ? 'Умеренная нагрузка' :
                 hasScore ? 'Хороший баланс' : 'Анализ завершён'}
              </h2>
              <p className="text-subheading">
                {pipelineResult.status === 'completed'
                  ? 'Конвейер завершил анализ данных. Coach Agent подготовил рекомендации.'
                  : `Статус: ${pipelineResult.status}`}
              </p>

              <div style={{ display: 'flex', gap: 12, marginTop: 32, flexWrap: 'wrap' }}>
                <button className="btn btn-yellow" onClick={() => onNavigate('chat')}>
                  Поговорить с Coach →
                </button>
                <button className="btn btn-black" onClick={() => onNavigate('plan')}>
                  Посмотреть план
                </button>
              </div>
            </div>
          </div>
        </div>

        {/* Coach message */}
        {hasMessage && (
          <div className="card" style={{ marginBottom: 24 }}>
            <div className="flex items-center gap-12" style={{ marginBottom: 20 }}>
              <span
                style={{
                  width: 40,
                  height: 40,
                  background: 'var(--color-yellow)',
                  borderRadius: '50%',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 20,
                  flexShrink: 0,
                }}
              >
                🤖
              </span>
              <div>
                <p className="text-body" style={{ fontWeight: 600 }}>Coach Agent</p>
                <p className="text-caption">Первичный анализ</p>
              </div>
            </div>
            <div
              style={{
                background: 'var(--color-mist)',
                borderRadius: 16,
                padding: '20px 24px',
                lineHeight: 1.7,
                fontSize: 15,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
              }}
            >
              {pipelineResult.coach_message}
            </div>
            <div className="btn-pair" style={{ marginTop: 24 }}>
              <button className="btn btn-yellow btn-sm" onClick={() => onNavigate('chat')}>
                Задать вопрос Coach
              </button>
              <button className="btn btn-black btn-sm" onClick={() => onNavigate('plan')}>
                Перейти к шагам плана
              </button>
            </div>
          </div>
        )}

        {/* Navigation cards */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16 }}>
          <button
            className="card-sm"
            style={{
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'transform 0.15s',
            }}
            onClick={() => onNavigate('chat')}
            onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-2px)')}
            onMouseLeave={e => (e.currentTarget.style.transform = '')}
          >
            <span style={{ fontSize: 32, display: 'block', marginBottom: 12 }}>💬</span>
            <p className="text-body" style={{ fontWeight: 600, marginBottom: 6 }}>Чат с Coach</p>
            <p className="text-caption">Задавай вопросы, получай советы</p>
          </button>

          <button
            className="card-sm"
            style={{
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'transform 0.15s',
            }}
            onClick={() => onNavigate('plan')}
            onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-2px)')}
            onMouseLeave={e => (e.currentTarget.style.transform = '')}
          >
            <span style={{ fontSize: 32, display: 'block', marginBottom: 12 }}>📋</span>
            <p className="text-body" style={{ fontWeight: 600, marginBottom: 6 }}>Шаги плана</p>
            <p className="text-caption">Принимай или отклоняй рекомендации</p>
          </button>

          <button
            className="card-sm"
            style={{
              border: 'none',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'transform 0.15s',
            }}
            onClick={() => onNavigate('privacy')}
            onMouseEnter={e => (e.currentTarget.style.transform = 'translateY(-2px)')}
            onMouseLeave={e => (e.currentTarget.style.transform = '')}
          >
            <span style={{ fontSize: 32, display: 'block', marginBottom: 12 }}>🔒</span>
            <p className="text-body" style={{ fontWeight: 600, marginBottom: 6 }}>Privacy Report</p>
            <p className="text-caption">Аудит всех операций с твоими данными</p>
          </button>
        </div>
      </div>
    </div>
  );
}
