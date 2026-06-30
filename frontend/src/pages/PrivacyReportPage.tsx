import { useEffect, useState } from 'react';
import { api } from '../api';
import type { PrivacyReportResponse } from '../types';

interface PrivacyReportPageProps {
  sessionId: string;
  cachedReport: PrivacyReportResponse | null;
  onReportLoaded: (report: PrivacyReportResponse) => void;
  onSessionEnded: () => void;
}

export function PrivacyReportPage({ sessionId, cachedReport, onReportLoaded, onSessionEnded }: PrivacyReportPageProps) {
  const [report, setReport] = useState<PrivacyReportResponse | null>(cachedReport);
  const [loading, setLoading] = useState(!cachedReport);
  const [error, setError] = useState<string | null>(null);
  const [ending, setEnding] = useState(false);
  const [showEndConfirm, setShowEndConfirm] = useState(false);

  useEffect(() => {
    if (cachedReport) return;
    api.getPrivacyReport(sessionId)
      .then(r => { setReport(r); onReportLoaded(r); })
      .catch(e => setError(e instanceof Error ? e.message : 'Failed to load report'))
      .finally(() => setLoading(false));
  }, [sessionId, cachedReport, onReportLoaded]);

  async function handleEndSession() {
    setEnding(true);
    try {
      await api.endSession(sessionId);
      onSessionEnded();
    } catch (e) {
      alert(`Error: ${e instanceof Error ? e.message : 'unknown error'}`);
      setEnding(false);
      setShowEndConfirm(false);
    }
  }

  if (loading) {
    return (
      <div className="page">
        <div className="container" style={{ paddingTop: 80, textAlign: 'center' }}>
          <span className="spinner spinner-lg" style={{ display: 'block', margin: '0 auto 24px' }} />
          <p className="text-body">Loading Privacy Report…</p>
        </div>
      </div>
    );
  }

  if (error || !report) {
    return (
      <div className="page">
        <div className="container" style={{ paddingTop: 80 }}>
          <div
            className="card"
            style={{
              textAlign: 'center',
              background: 'rgba(243,70,70,0.06)',
              border: '1.5px solid var(--color-red)',
            }}
          >
            <p className="text-body" style={{ color: 'var(--color-red)', fontWeight: 500 }}>
              ⚠️ {error ?? 'Could not load the report'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="container" style={{ paddingTop: 48 }}>

        {/* Clean / Not-clean banner */}
        <div
          style={{
            background: report.is_clean ? 'rgba(70,108,243,0.07)' : 'rgba(243,70,70,0.07)',
            border: `2px solid ${report.is_clean ? 'var(--color-blue)' : 'var(--color-red)'}`,
            borderRadius: 24,
            padding: '28px 36px',
            marginBottom: 24,
            display: 'flex',
            alignItems: 'center',
            gap: 20,
          }}
        >
          <span style={{ fontSize: 48 }}>{report.is_clean ? '🛡️' : '⚠️'}</span>
          <div>
            <p
              className="text-heading-sm"
              style={{ color: report.is_clean ? 'var(--color-blue)' : 'var(--color-red)', marginBottom: 6 }}
            >
              {report.is_clean ? 'All clear' : 'Violations detected'}
            </p>
            <p className="text-body" style={{ opacity: 0.7 }}>
              {report.is_clean
                ? 'Guard Agent recorded no privacy policy violations in this session.'
                : `Guard Agent blocked ${report.policy_violations_blocked} policy violation(s).`}
            </p>
          </div>
        </div>

        {/* Stats grid */}
        <div
          className="card"
          style={{
            marginBottom: 24,
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
            gap: 32,
          }}
        >
          <div className="privacy-stat">
            <span className="privacy-stat-value">{report.events_count}</span>
            <span className="privacy-stat-label">Events logged</span>
          </div>
          <div className="privacy-stat">
            <span className="privacy-stat-value">{report.policy_violations_blocked}</span>
            <span className="privacy-stat-label" style={{ color: report.policy_violations_blocked > 0 ? 'var(--color-red)' : undefined }}>
              Violations blocked
            </span>
          </div>
          <div className="privacy-stat">
            <span
              className="privacy-stat-value"
              style={{ color: report.raw_data_persisted ? 'var(--color-red)' : 'var(--color-blue)', fontSize: 28 }}
            >
              {report.raw_data_persisted ? 'Yes' : 'No'}
            </span>
            <span className="privacy-stat-label">Raw data persisted</span>
          </div>
          <div className="privacy-stat">
            <span className="privacy-stat-value">{report.external_calls_made.length}</span>
            <span className="privacy-stat-label">External requests</span>
          </div>
        </div>

        {/* External calls */}
        <div className="card" style={{ marginBottom: 24 }}>
          <p className="text-body" style={{ fontWeight: 600, marginBottom: 16 }}>
            External requests ({report.external_calls_made.length})
          </p>
          {report.external_calls_made.length === 0 ? (
            <div
              style={{
                background: 'rgba(70,108,243,0.05)',
                borderRadius: 12,
                padding: '16px 20px',
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}
            >
              <span style={{ fontSize: 20 }}>✅</span>
              <p className="text-body" style={{ opacity: 0.7 }}>
                No external requests — all computations were performed locally.
              </p>
            </div>
          ) : (
            <div className="flex flex-col gap-8">
              {report.external_calls_made.map((call, i) => (
                <div
                  key={i}
                  style={{
                    background: 'var(--color-mist)',
                    borderRadius: 10,
                    padding: '10px 16px',
                    fontFamily: 'var(--font-inter)',
                    fontSize: 13,
                    wordBreak: 'break-all',
                  }}
                >
                  {call}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Session ID */}
        <div className="card" style={{ marginBottom: 24 }}>
          <p className="text-body" style={{ fontWeight: 600, marginBottom: 8 }}>Session ID</p>
          <code
            style={{
              fontFamily: 'monospace',
              fontSize: 13,
              background: 'var(--color-mist)',
              borderRadius: 8,
              padding: '8px 14px',
              display: 'block',
              wordBreak: 'break-all',
              color: 'var(--color-carbon)',
              opacity: 0.8,
            }}
          >
            {report.session_id}
          </code>
        </div>

        {/* End session */}
        {!showEndConfirm ? (
          <div className="btn-pair">
            <button className="btn btn-yellow" onClick={() => window.location.reload()}>
              Start over
            </button>
            <button
              className="btn btn-ghost-red"
              onClick={() => setShowEndConfirm(true)}
            >
              🗑 End session & delete data
            </button>
          </div>
        ) : (
          <div
            style={{
              background: 'rgba(243,70,70,0.07)',
              border: '1.5px solid var(--color-red)',
              borderRadius: 20,
              padding: '24px 28px',
            }}
          >
            <p className="text-body" style={{ fontWeight: 600, marginBottom: 8 }}>
              Confirm ending session?
            </p>
            <p className="text-caption" style={{ marginBottom: 20, fontSize: 14 }}>
              Guard Agent will erase all session data from memory. This action is irreversible.
            </p>
            <div className="btn-pair">
              <button
                className="btn btn-black"
                disabled={ending}
                onClick={handleEndSession}
              >
                {ending ? <span className="flex items-center gap-8"><span className="spinner" />Deleting…</span> : 'Yes, delete data'}
              </button>
              <button
                className="btn btn-ghost"
                disabled={ending}
                onClick={() => setShowEndConfirm(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
