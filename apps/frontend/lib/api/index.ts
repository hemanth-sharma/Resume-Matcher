/**
 * API Module Exports
 *
 * Centralized exports for all API-related functionality.
 */

// Client utilities
export {
  API_URL,
  API_BASE,
  apiFetch,
  apiPost,
  apiPatch,
  apiPut,
  apiDelete,
  getUploadUrl,
} from './client';

// Resume operations
export {
  uploadJobDescriptions,
  improveResume,
  previewImproveResume,
  confirmImproveResume,
  fetchResume,
  fetchResumeList,
  updateResume,
  downloadResumePdf,
  deleteResume,
  type ResumeListItem,
} from './resume';

// Resume wizard operations
export {
  createInitialResumeWizardState,
  finalizeResumeWizard,
  postResumeWizardTurn,
  type ResumeWizardAction,
  type ResumeWizardFinalizeResponse,
  type ResumeWizardSection,
  type ResumeWizardState,
  type ResumeWizardStep,
  type ResumeWizardTurnRequest,
  type ResumeWizardTurnResponse,
} from './resume-wizard';

// Config operations
export {
  fetchLlmConfig,
  fetchLlmApiKey,
  updateLlmConfig,
  updateLlmApiKey,
  testLlmConnection,
  fetchSystemStatus,
  PROVIDER_INFO,
  fetchPromptConfig,
  updatePromptConfig,
  type LLMProvider,
  type LLMConfig,
  type LLMConfigUpdate,
  type DatabaseStats,
  type SystemStatus,
  type LLMHealthCheck,
  type PromptOption,
  type PromptConfig,
  type PromptConfigUpdate,
} from './config';

// Standalone ATS check operations
export {
  uploadAtsCheck,
  listAtsChecks,
  getAtsCheckDetail,
  deleteAtsCheck,
  type AtsCheck,
  type AtsScoreData,
  type AtsScoreDetails,
  type AtsCheckListResponse,
  type AtsCheckDeleteResponse,
} from './ats-check';
