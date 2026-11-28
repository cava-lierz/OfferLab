export type Status = 'preparing' | 'ready' | 'active' | 'awaiting_next' | 'between_questions' | 'reporting' | 'completed'
export type Question = { id: string; text: string; topic: string; main_index: number; followup: number }
export type Excerpt = { id: string; path: string; code: string } & (
  { page?: undefined; start: number; end: number; url: string } |
  { page: number; note?: string; truncated?: boolean }
)
export type Project = { id: string; title: string; sha: string; excerpts: Excerpt[]; target_role?: string } & (
  { kind?: 'pr'; url: string; file_count: number; scanned_files: number } |
  { kind: 'pdf'; page_count: number }
)
export type ProjectForm = { claim: string; preview_id: string; excerpt_ids: string[]; target_role: string; requirement: string; page_notes: Record<string, string> }
export type Coaching = { answer_id: string; answer_quote: string; excerpt_id: string; source_field: 'code' | 'note'; work_quote: string; match: string; gap: string; resume_line: string }
export type Answer = { excerpt_id?: string; id: string; request_id: string; text: string; question: Question }
export type Generation = {
  id: string; task: 'plan' | 'decision' | 'report'
  status: 'queued' | 'running' | 'completed' | 'failed'
  phase: 'queued' | 'generating' | 'validating' | 'completed' | 'failed'
  queued_at: number; started_at?: number; deadline_at?: number; finished_at?: number; timeout_seconds: number
}
export type PreparationResearch = {
  status: 'used' | 'no_match' | 'unavailable' | 'skipped'
  sources: { title: string; url: string }[]
}
export type Report = {
  coaching?: Coaching
  summary: string
  dimensions: { name: string; score: number | null; feedback: string; suggestion: string; evidence: { answer_id: string; quote: string }[] }[]
  sources: PreparationResearch['sources']
  source_note: string
}
export type Interview = {
  adopted_resume_line?: string
  project?: Project
  id: string; role: string; resume: string; jd: string; practice_focus?: string; main_count: number; mode: 'demo' | 'openclaw'
  research?: PreparationResearch | null
  status: Status; plan: { topic: string; question: string }[]; current: Question | null
  answers: Answer[]; report: Report | null; error: string | null; created_at: number; updated_at: number
  generation?: Generation | null; revision?: number
}
export type History = Pick<Interview, 'id' | 'role' | 'status' | 'mode' | 'created_at' | 'updated_at' | 'main_count' | 'generation' | 'error' | 'revision'> & { answered: number }
export type Health = { mode: 'demo' | 'openclaw'; token_configured: boolean; request_timeout_seconds?: number; report_timeout_seconds?: number }
export type Preparation = { role: string; resume: string; jd: string; practice_focus?: string; main_count: number }
