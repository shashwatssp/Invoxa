import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '';
const TOKEN_KEY = 'invoxa_token';

export const api = axios.create({
  baseURL,
  timeout: 120_000, // generous; backend may cold-start on free hosting tiers
});

// Attach the bearer token to every request when present.
api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

/** Registered by AuthContext: fires once on any 401 (invalid/expired session). */
let onUnauthorized: (() => void) | null = null;
export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (axios.isAxiosError(error) && error.response?.status === 401 && onUnauthorized) {
      onUnauthorized();
    }
    return Promise.reject(error);
  },
);

export function storeToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}
export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}
export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/** Map any request failure to user-facing copy. Never leaks backend internals. */
export function friendlyError(err: unknown, fallback = 'Something went wrong. Please try again.'): string {
  if (axios.isAxiosError(err)) {
    if (!err.response) {
      return 'Cannot reach the service. Check your connection and try again.';
    }
    const status = err.response.status;
    if (status === 503) return 'The service is warming up. Give it a moment, then retry.';
    if (status === 502 || status === 504) return 'The service is unavailable right now. Try again shortly.';
    if (status === 404) return 'That item could not be found.';
    if (status >= 500) return 'Something went wrong on our side. Please try again.';
    const detail = (err.response.data as { detail?: string } | undefined)?.detail;
    if (status === 400 && detail) return detail;
  }
  return fallback;
}

export interface AuthUser {
  id: string;
  email: string;
  name: string | null;
  role: 'member' | 'approver';
}

export interface AuthResponse {
  token: string;
  user: AuthUser;
}

export interface HealthResponse {
  status: 'ok' | string;
}

export interface InvoiceSummary {
  id: string;
  vendor_id: string | null;
  invoice_number: string | null;
  amount: number | null;
  due_date: string | null;
  status: string;
  storage_path: string;
  created_at: string;
}

export interface ExtractionField {
  field_name: string;
  raw_value: string | null;
  confidence: number | null;
  created_at: string;
}

export interface InvoiceDetail extends InvoiceSummary {
  extraction_fields: ExtractionField[];
}

export interface ExtractedFields {
  vendor_name?: string | null;
  vendor_gstin?: string | null;
  invoice_number?: string | null;
  invoice_date?: string | null;
  due_date?: string | null;
  amount?: number | null;
  tax_amount?: number | null;
  total_amount?: number | null;
  overall_confidence?: number | null;
  needs_review?: boolean;
}

export interface UploadResponse {
  id: string;
  storage_path: string;
  extraction?: ExtractedFields;
}

export interface ReviewQueueItem {
  id: string;
  invoice_id: string;
  reason: string;
  status: 'pending' | 'approved' | 'rejected';
  created_at: string;
  invoices?: {
    status: string;
    vendor_id: string | null;
    invoice_number: string | null;
    amount: number | null;
    storage_path?: string;
  };
}

export async function signup(email: string, password: string, name: string): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/api/auth/signup', {
    email,
    password,
    name: name || null,
  });
  return data;
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  const { data } = await api.post<AuthResponse>('/api/auth/login', { email, password });
  return data;
}

export async function fetchMe(): Promise<AuthUser> {
  const { data } = await api.get<AuthUser>('/api/auth/me');
  return data;
}

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health');
  return data;
}

/** Fetch the original receipt PDF as a Blob for inline viewing. */
export async function fetchInvoiceFile(invoiceId: string): Promise<Blob> {
  const { data } = await api.get<Blob>(`/api/invoices/${invoiceId}/file`, {
    responseType: 'blob',
  });
  return data;
}

/** Download the approved-invoices CSV via authenticated blob (no URL leaks). */
export async function downloadCsv(status?: string): Promise<void> {
  const { data } = await api.get<Blob>('/api/export/csv', {
    responseType: 'blob',
    params: status ? { status } : undefined,
  });
  const url = URL.createObjectURL(data);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `invoxa_export_${status || 'all'}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export async function fetchInvoices(): Promise<InvoiceSummary[]> {
  const { data } = await api.get<InvoiceSummary[]>('/api/invoices');
  return data;
}

export async function fetchInvoice(id: string): Promise<InvoiceDetail> {
  const { data } = await api.get<InvoiceDetail>(`/api/invoices/${id}`);
  return data;
}

export async function uploadInvoice(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file, file.name);
  const { data } = await api.post<UploadResponse>('/api/invoices/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  });
  return data;
}

export async function fetchReviewQueue(): Promise<ReviewQueueItem[]> {
  const { data } = await api.get<ReviewQueueItem[]>('/api/review/queue');
  return data;
}

export async function resolveReview(reviewId: string, approved: boolean): Promise<void> {
  await api.post(`/api/review/${reviewId}/resolve`, null, { params: { approved } });
}

export async function submitCorrection(
  reviewId: string,
  fieldName: string,
  newValue: string,
): Promise<void> {
  await api.post(`/api/review/${reviewId}/correct`, { field_name: fieldName, new_value: newValue });
}

export async function fetchDigest(days: number): Promise<Record<string, unknown>> {
  const { data } = await api.get('/api/digest', { params: { days } });
  return data;
}

export function buildCsvDownloadUrl(status?: string): string {
  const trimmed = baseURL.replace(/\/$/, '');
  const params = status ? `?status=${encodeURIComponent(status)}` : '';
  return `${trimmed}/api/export/csv${params}`;
}
