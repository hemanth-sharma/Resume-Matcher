import { apiFetch, apiDelete } from './client';

// ---------------------------------------------------------------------------
// Types (mirror app/schemas/ats_check.py in the backend)
// ---------------------------------------------------------------------------

/** One standalone ATS check record (list form — no bulky content). */
export interface AtsCheck {
  id: number;
  file_name: string;
  stored_path: string | null;
  status: 'processing' | 'ready' | 'failed';
  overall_score: number | null;
  sub_scores: Record<string, number> | null;
  score_data: AtsScoreData | null;
  source: 'manual' | 'folder_watch';
  error: string | null;
  created_at: string;
  updated_at: string;
}

/** Full standalone ATS payload (shape mirrors the JD-aware engine's output). */
export interface AtsScoreData {
  overall_score: number;
  sub_scores: Record<string, number>;
  recommendations: string[];
  interpretation: string;
  details: AtsScoreDetails | null;
}

export interface AtsScoreDetails {
  contact?: {
    email: boolean;
    phone: boolean;
    professional_link: boolean;
    location: boolean;
    name_line: boolean;
  };
  sections?: {
    found: string[];
    missing: string[];
  };
  formatting?: {
    total_words: number;
    bullet_lines: number;
    well_sized_bullets: number;
    date_ranges_found: number;
    table_artifacts: number;
    formatting_warnings: string[];
  };
  impact?: {
    quantified_bullets: number;
    action_verb_bullets: number;
    total_bullets: number;
  };
  keywords?: {
    distinct_known_skills: number;
    known_skills_found: string[];
    keyword_stuffing: boolean;
  };
  readability?: {
    filler_phrases: number;
    first_person_pronouns: number;
    all_caps_words: number;
    long_lines: number;
    readability_warnings: string[];
  };
}

export interface AtsCheckListResponse {
  checks: AtsCheck[];
}

export interface AtsCheckDeleteResponse {
  message: string;
  deleted_id: number;
}

// ---------------------------------------------------------------------------
// Error helpers (same pattern as tracker.ts)
// ---------------------------------------------------------------------------

function extractDetail(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((d) =>
        d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : null
      )
      .filter((m): m is string => Boolean(m));
    if (messages.length > 0) return messages.join('; ');
  }
  if (detail && typeof detail === 'object' && !Array.isArray(detail)) {
    try {
      return JSON.stringify(detail);
    } catch {
      return null;
    }
  }
  return null;
}

async function asJson<T>(res: Response, fallback: string): Promise<T> {
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error(extractDetail(data) || `${fallback} (status ${res.status}).`);
  }
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// API calls
// ---------------------------------------------------------------------------

/** Upload a resume PDF for a standalone ATS check and return the scored record. */
export async function uploadAtsCheck(
  file: File,
  source: 'manual' | 'folder_watch' = 'manual'
): Promise<AtsCheck> {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('source', source);
  const res = await apiFetch('/ats-check/upload', {
    method: 'POST',
    body: formData,
  });
  return asJson<AtsCheck>(res, 'Failed to check the resume');
}

/** List all standalone ATS checks, newest first. */
export async function listAtsChecks(): Promise<AtsCheckListResponse> {
  const res = await apiFetch('/ats-check/checks');
  return asJson<AtsCheckListResponse>(res, 'Failed to load ATS checks');
}

/** Fetch one ATS check with its full score payload. */
export async function getAtsCheckDetail(id: number | string): Promise<AtsCheck> {
  const res = await apiFetch(`/ats-check/checks/${id}`);
  return asJson<AtsCheck>(res, 'Failed to load the ATS check');
}

/** Delete an ATS check record (and its archived PDF copy on the backend). */
export async function deleteAtsCheck(id: number): Promise<AtsCheckDeleteResponse> {
  const res = await apiDelete(`/ats-check/checks/${id}`);
  return asJson<AtsCheckDeleteResponse>(res, 'Failed to delete the ATS check');
}
