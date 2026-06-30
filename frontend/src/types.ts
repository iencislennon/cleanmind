export type DataSource =
  | 'apple_screen_time'
  | 'google_digital_wellbeing'
  | 'tiktok_export'
  | 'instagram_export';

export interface UploadFileRequest {
  source: DataSource;
  file_content_base64: string;
  filename: string;
}

export interface StartSessionResponse {
  session_id: string;
}

export interface PipelineStatusResponse {
  session_id: string;
  status: string;
  overload_score: number | null;
  severity_label: string | null;
  coach_message: string | null;
  error_message: string | null;
}

export interface ChatMessageRequest {
  session_id: string;
  message: string;
}

export interface ChatMessageResponse {
  session_id: string;
  agent_reply: string;
}

export interface StepDecisionRequest {
  session_id: string;
  plan_id: string;
  step_id: string;
  decision: 'accepted' | 'rejected' | 'completed';
}

export interface StepDecisionResponse {
  status: string;
  updated_plan: string | null;
}

export interface PrivacyReportResponse {
  session_id: string;
  is_clean: boolean;
  events_count: number;
  raw_data_persisted: boolean;
  external_calls_made: string[];
  policy_violations_blocked: number;
}

export interface PlanStep {
  step_id: string;
  title: string;
  description: string;
  status: 'pending' | 'accepted' | 'rejected' | 'completed';
}

export interface CoachPlan {
  plan_id: string;
  steps: PlanStep[];
  summary?: string;
}

export type ChatRole = 'user' | 'coach';

export interface ChatMessage {
  id: string;
  role: ChatRole;
  text: string;
  ts: number;
}

export type AppView = 'upload' | 'processing' | 'dashboard' | 'chat' | 'plan' | 'privacy';

export interface AppState {
  view: AppView;
  sessionId: string | null;
  pipelineResult: PipelineStatusResponse | null;
  plan: CoachPlan | null;
  chatHistory: ChatMessage[];
  privacyReport: PrivacyReportResponse | null;
}
