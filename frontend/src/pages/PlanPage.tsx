import { useState } from 'react';
import { api } from '../api';
import type { CoachPlan, PlanStep } from '../types';

interface PlanPageProps {
  sessionId: string;
  plan: CoachPlan | null;
  onPlanUpdate: (plan: CoachPlan) => void;
  coachMessage: string | null;
  onGoToChat: () => void;
}

const STATUS_LABEL: Record<PlanStep['status'], string> = {
  pending: 'Awaiting decision',
  accepted: '✓ Accepted',
  rejected: '✗ Declined',
  completed: '✔ Completed',
};

const STATUS_TAG: Record<PlanStep['status'], string> = {
  pending: '',
  accepted: 'tag-yellow',
  rejected: '',
  completed: 'tag-blue',
};

function StepCard({
  step,
  index,
  planId,
  sessionId,
  onUpdate,
}: {
  step: PlanStep;
  index: number;
  planId: string;
  sessionId: string;
  onUpdate: (updated: PlanStep) => void;
}) {
  const [loading, setLoading] = useState<string | null>(null);

  async function decide(decision: 'accepted' | 'rejected' | 'completed') {
    setLoading(decision);
    try {
      await api.submitStepDecision({
        session_id: sessionId,
        plan_id: planId,
        step_id: step.step_id,
        decision,
      });
      onUpdate({ ...step, status: decision });
    } catch (err) {
      alert(`Error: ${err instanceof Error ? err.message : 'unknown error'}`);
    } finally {
      setLoading(null);
    }
  }

  const isDecided = step.status !== 'pending';

  return (
    <div className={`step-card ${step.status}`}>
      <div className="flex items-start gap-16">
        <span className="step-number">{index + 1}</span>
        <div style={{ flex: 1 }}>
          <div className="flex items-center justify-between gap-16" style={{ flexWrap: 'wrap', marginBottom: 8 }}>
            <p className="text-body" style={{ fontWeight: 600 }}>{step.title}</p>
            {isDecided && (
              <span className={`tag ${STATUS_TAG[step.status]}`} style={{ fontSize: 12, flexShrink: 0 }}>
                {STATUS_LABEL[step.status]}
              </span>
            )}
          </div>
          <p className="text-body" style={{ opacity: 0.7, marginBottom: isDecided ? 0 : 20, lineHeight: 1.6 }}>
            {step.description}
          </p>

          {!isDecided && (
            <div className="flex gap-8" style={{ flexWrap: 'wrap' }}>
              <button
                className="btn btn-yellow btn-sm"
                disabled={loading !== null}
                onClick={() => decide('accepted')}
              >
                {loading === 'accepted' ? <span className="spinner" /> : '✓ Accept'}
              </button>
              <button
                className="btn btn-black btn-sm"
                disabled={loading !== null}
                onClick={() => decide('completed')}
              >
                {loading === 'completed' ? <span className="spinner" /> : '✔ Mark done'}
              </button>
              <button
                className="btn btn-ghost-red btn-sm"
                disabled={loading !== null}
                onClick={() => decide('rejected')}
              >
                {loading === 'rejected' ? <span className="spinner" /> : '✗ Decline'}
              </button>
            </div>
          )}

          {step.status === 'accepted' && (
            <button
              className="btn btn-black btn-sm"
              style={{ marginTop: 12 }}
              disabled={loading !== null}
              onClick={() => decide('completed')}
            >
              {loading === 'completed' ? <span className="spinner" /> : 'Mark as completed'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function PlanPage({ sessionId, plan, onPlanUpdate, coachMessage, onGoToChat }: PlanPageProps) {
  const [localPlan, setLocalPlan] = useState<CoachPlan | null>(plan);

  function handleStepUpdate(updatedStep: PlanStep) {
    if (!localPlan) return;
    const updatedSteps = localPlan.steps.map(s =>
      s.step_id === updatedStep.step_id ? updatedStep : s
    );
    const updated = { ...localPlan, steps: updatedSteps };
    setLocalPlan(updated);
    onPlanUpdate(updated);
  }

  if (!localPlan) {
    return (
      <div className="page">
        <div className="container" style={{ paddingTop: 48 }}>
          <div className="card" style={{ textAlign: 'center', padding: '64px 40px' }}>
            <span style={{ fontSize: 56, display: 'block', marginBottom: 24 }}>📋</span>
            <h2 className="text-heading-sm" style={{ marginBottom: 16 }}>
              No structured plan yet
            </h2>
            <p className="text-subheading" style={{ maxWidth: 440, margin: '0 auto 32px' }}>
              Coach Agent returns recommendations as text. Go to chat to get a plan
              or ask follow-up questions.
            </p>
            {coachMessage && (
              <div
                style={{
                  background: 'var(--color-mist)',
                  borderRadius: 16,
                  padding: '20px 24px',
                  textAlign: 'left',
                  lineHeight: 1.7,
                  fontSize: 15,
                  marginBottom: 32,
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-word',
                }}
              >
                {coachMessage}
              </div>
            )}
            <div className="btn-pair" style={{ justifyContent: 'center' }}>
              <button className="btn btn-yellow" onClick={onGoToChat}>
                Open chat with Coach →
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const acceptedCount = localPlan.steps.filter(s => s.status === 'accepted' || s.status === 'completed').length;
  const completedCount = localPlan.steps.filter(s => s.status === 'completed').length;
  const progress = localPlan.steps.length > 0
    ? Math.round((completedCount / localPlan.steps.length) * 100)
    : 0;

  return (
    <div className="page">
      <div className="container" style={{ paddingTop: 48 }}>

        {/* Header */}
        <div className="flex items-center justify-between" style={{ marginBottom: 32, flexWrap: 'wrap', gap: 16 }}>
          <div>
            <h2 className="text-heading-sm" style={{ marginBottom: 6 }}>Your action plan</h2>
            <p className="text-subheading">
              {acceptedCount} of {localPlan.steps.length} steps accepted · {completedCount} completed
            </p>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onGoToChat}>
            💬 Discuss with Coach
          </button>
        </div>

        {/* Progress bar */}
        <div
          style={{
            background: 'var(--color-white)',
            borderRadius: 8,
            height: 8,
            marginBottom: 32,
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: '100%',
              background: 'var(--color-yellow)',
              borderRadius: 8,
              transition: 'width 0.4s ease',
            }}
          />
        </div>

        {/* Steps */}
        <div className="flex flex-col gap-16">
          {localPlan.steps.map((step, i) => (
            <StepCard
              key={step.step_id}
              step={step}
              index={i}
              planId={localPlan.plan_id}
              sessionId={sessionId}
              onUpdate={handleStepUpdate}
            />
          ))}
        </div>

        {/* Summary block */}
        {localPlan.summary && (
          <div className="card" style={{ marginTop: 32 }}>
            <p className="text-body" style={{ fontWeight: 600, marginBottom: 12 }}>Coach Agent summary</p>
            <p className="text-body" style={{ lineHeight: 1.7, opacity: 0.8 }}>{localPlan.summary}</p>
          </div>
        )}
      </div>
    </div>
  );
}
