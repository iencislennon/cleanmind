import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import type { ChatMessage } from '../types';

interface ChatPageProps {
  sessionId: string;
  initialMessages: ChatMessage[];
  onMessagesUpdate: (messages: ChatMessage[]) => void;
  initialCoachMessage: string | null;
}

let msgIdCounter = 0;
function nextId() { return `msg-${++msgIdCounter}`; }

export function ChatPage({ sessionId, initialMessages, onMessagesUpdate, initialCoachMessage }: ChatPageProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    if (initialMessages.length > 0) return initialMessages;
    if (initialCoachMessage) {
      return [{
        id: nextId(),
        role: 'coach' as const,
        text: initialCoachMessage,
        ts: Date.now(),
      }];
    }
    return [{
      id: nextId(),
      role: 'coach' as const,
      text: "Hi! I'm Coach Agent. I've analysed your screen time data. Ask me about the results or how to get started with your plan.",
      ts: Date.now(),
    }];
  });

  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  useEffect(() => {
    onMessagesUpdate(messages);
  }, [messages, onMessagesUpdate]);

  function autoResize() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 140) + 'px';
  }

  async function handleSend() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = { id: nextId(), role: 'user', text, ts: Date.now() };
    const next = [...messages, userMsg];
    setMessages(next);
    setInput('');
    if (textareaRef.current) textareaRef.current.style.height = 'auto';
    setLoading(true);

    try {
      const res = await api.sendChatMessage({ session_id: sessionId, message: text });
      const coachMsg: ChatMessage = {
        id: nextId(),
        role: 'coach',
        text: res.agent_reply || '…',
        ts: Date.now(),
      };
      setMessages(m => [...m, coachMsg]);
    } catch (err) {
      const errMsg: ChatMessage = {
        id: nextId(),
        role: 'coach',
        text: `Error communicating with Coach Agent: ${err instanceof Error ? err.message : 'unknown error'}`,
        ts: Date.now(),
      };
      setMessages(m => [...m, errMsg]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const SUGGESTIONS = [
    'Which apps take up the most time?',
    'Give me the first step to improve',
    'What does my overload score mean?',
    'How can I reduce social media anxiety?',
  ];

  return (
    <div className="page">
      <div className="container" style={{ paddingTop: 40 }}>
        <div
          className="card"
          style={{
            display: 'flex',
            flexDirection: 'column',
            height: 'calc(100vh - 200px)',
            minHeight: 500,
            maxHeight: 800,
            padding: '32px 32px 24px',
          }}
        >
          {/* Header */}
          <div
            className="flex items-center gap-16"
            style={{ paddingBottom: 20, borderBottom: '1.5px solid var(--color-hairline)', marginBottom: 20, flexShrink: 0 }}
          >
            <div
              style={{
                width: 44,
                height: 44,
                background: 'var(--color-yellow)',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                fontSize: 22,
                flexShrink: 0,
              }}
            >
              🤖
            </div>
            <div>
              <p className="text-body" style={{ fontWeight: 600 }}>Coach Agent</p>
              <p className="text-caption">
                {loading ? 'typing…' : 'online'}
              </p>
            </div>
          </div>

          {/* Messages */}
          <div
            className="chat-messages"
            style={{ flex: 1, overflowY: 'auto', paddingRight: 4 }}
          >
            {messages.map(msg => (
              <div key={msg.id} className={`chat-bubble ${msg.role}`}>
                {msg.text}
              </div>
            ))}
            {loading && (
              <div className="chat-bubble coach">
                <span className="flex items-center gap-8">
                  <span className="spinner" />
                  Coach is thinking…
                </span>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Suggestions (shown when only 1 message) */}
          {messages.length <= 1 && (
            <div
              style={{
                display: 'flex',
                gap: 8,
                flexWrap: 'wrap',
                paddingTop: 12,
                paddingBottom: 4,
                flexShrink: 0,
              }}
            >
              {SUGGESTIONS.map(s => (
                <button
                  key={s}
                  className="tag"
                  style={{ fontSize: 13 }}
                  onClick={() => { setInput(s); textareaRef.current?.focus(); }}
                >
                  {s}
                </button>
              ))}
            </div>
          )}

          {/* Input bar */}
          <div className="chat-input-bar" style={{ flexShrink: 0 }}>
            <textarea
              ref={textareaRef}
              className="chat-textarea"
              placeholder="Message Coach Agent…"
              rows={1}
              value={input}
              onChange={e => { setInput(e.target.value); autoResize(); }}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button
              className="btn btn-yellow btn-sm"
              style={{ flexShrink: 0, alignSelf: 'flex-end' }}
              onClick={handleSend}
              disabled={!input.trim() || loading}
            >
              ↑ Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
