import { useRef, useState } from 'react';
import type { DataSource } from '../types';
import { api, fileToBase64 } from '../api';

interface UploadPageProps {
  onSessionStarted: (sessionId: string) => void;
  onPipelineComplete: (sessionId: string, pipelineResult: import('../types').PipelineStatusResponse) => void;
  onError: (message: string) => void;
}

const SOURCES: { value: DataSource; label: string; icon: string; hint: string }[] = [
  { value: 'apple_screen_time', label: 'Apple Screen Time', icon: '🍎', hint: 'Settings → Screen Time → Export' },
  { value: 'google_digital_wellbeing', label: 'Google Wellbeing', icon: '🤖', hint: 'Settings → Digital Wellbeing → Export' },
  { value: 'tiktok_export', label: 'TikTok Export', icon: '🎵', hint: 'Profile → Settings → Privacy → Data' },
  { value: 'instagram_export', label: 'Instagram Export', icon: '📷', hint: 'Settings → Security → Download Data' },
];

export function UploadPage({ onSessionStarted, onPipelineComplete, onError }: UploadPageProps) {
  const [source, setSource] = useState<DataSource | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [loading, setLoading] = useState(false);
  const [phase, setPhase] = useState<'idle' | 'session' | 'pipeline'>('idle');
  const fileInputRef = useRef<HTMLInputElement>(null);

  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) setFile(dropped);
  }

  function handleFileInput(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  }

  async function handleSubmit() {
    if (!source || !file) return;
    setLoading(true);
    try {
      setPhase('session');
      const { session_id } = await api.startSession();
      onSessionStarted(session_id);

      setPhase('pipeline');
      const b64 = await fileToBase64(file);
      const result = await api.runPipeline(session_id, {
        source,
        file_content_base64: b64,
        filename: file.name,
      });
      onPipelineComplete(session_id, result);
    } catch (err) {
      onError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
      setPhase('idle');
    }
  }

  const canSubmit = source !== null && file !== null && !loading;

  const phaseLabel =
    phase === 'session' ? 'Creating session…'
    : phase === 'pipeline' ? 'Analyzing data… (up to 30 sec)'
    : '';

  return (
    <div className="page">
      <div className="container" style={{ paddingTop: 80 }}>
        {/* Hero */}
        <div className="text-center" style={{ marginBottom: 64 }}>
          <h1 className="text-heading" style={{ marginBottom: 16 }}>
            Discover your level of<br />
            <span style={{ background: 'var(--color-yellow)', borderRadius: 8, padding: '0 12px', display: 'inline-block' }}>
              information overload
            </span> 🧠
          </h1>
          <p className="text-subheading" style={{ marginTop: 20, maxWidth: 520, margin: '20px auto 0' }}>
            Upload your screen time export — Coach Agent will assess the load and suggest a personalised plan.
          </p>
        </div>

        {/* Upload card */}
        <div className="card" style={{ maxWidth: 640, margin: '0 auto' }}>

          {/* Source selector */}
          <div style={{ marginBottom: 32 }}>
            <p className="text-body" style={{ fontWeight: 500, marginBottom: 16 }}>
              1. Choose your data source
            </p>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
              {SOURCES.map(({ value, label, icon, hint }) => (
                <button
                  key={value}
                  className={`tag${source === value ? ' selected' : ''}`}
                  style={{
                    justifyContent: 'flex-start',
                    padding: '12px 16px',
                    borderRadius: 16,
                    gap: 10,
                    textAlign: 'left',
                    flexDirection: 'column',
                    alignItems: 'flex-start',
                    height: 'auto',
                    lineHeight: 1.4,
                  }}
                  onClick={() => setSource(value)}
                >
                  <span style={{ fontSize: 20 }}>{icon}</span>
                  <span style={{ fontWeight: 500, fontSize: 14 }}>{label}</span>
                  <span style={{ fontSize: 12, opacity: 0.6, fontWeight: 400 }}>{hint}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Drop zone */}
          <div style={{ marginBottom: 32 }}>
            <p className="text-body" style={{ fontWeight: 500, marginBottom: 16 }}>
              2. Upload your file
            </p>
            <div
              className={`drop-zone${dragOver ? ' drag-over' : ''}${file ? ' has-file' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept=".json,.csv,.xml,.zip,.txt"
                onChange={handleFileInput}
              />
              {file ? (
                <div className="flex flex-col items-center gap-12">
                  <span style={{ fontSize: 36 }}>📄</span>
                  <p className="text-body" style={{ fontWeight: 500 }}>{file.name}</p>
                  <p className="text-caption">{(file.size / 1024).toFixed(1)} KB · click to replace</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-12">
                  <span style={{ fontSize: 40 }}>☁️</span>
                  <p className="text-body" style={{ fontWeight: 500 }}>Drag & drop a file or click to browse</p>
                  <p className="text-caption">.json, .csv, .xml, .zip, .txt</p>
                </div>
              )}
            </div>
          </div>

          {/* Submit */}
          <div className="btn-pair" style={{ justifyContent: 'center' }}>
            <button className="btn btn-yellow" disabled={!canSubmit} onClick={handleSubmit}>
              {loading ? (
                <span className="flex items-center gap-8">
                  <span className="spinner" />
                  {phaseLabel}
                </span>
              ) : 'Analyze →'}
            </button>
            <button className="btn btn-black" disabled={loading} onClick={() => { setFile(null); setSource(null); }}>
              Reset
            </button>
          </div>
        </div>

        {/* Privacy note */}
        <p className="text-caption text-center" style={{ marginTop: 32, maxWidth: 480, margin: '32px auto 0' }}>
          🔒 Data is processed within a single session and is not retained after it ends.
          Guard Agent audits all operations.
        </p>
      </div>
    </div>
  );
}
