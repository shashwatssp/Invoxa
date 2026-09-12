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
  vendor_name?: string | null;
  invoice_number: string | null;
  amount: number | null;
  due_date: string | null;
  status: string;
  storage_path: string;
  created_at: string;
  folder_id: string | null;
}

export interface FolderInfo {
  id: string;
  name: string;
  invoice_count: number;
  created_at: string;
}

export async function fetchFolders(): Promise<FolderInfo[]> {
  const { data } = await api.get<FolderInfo[]>('/api/folders');
  return data;
}

export async function createFolder(name: string): Promise<{ id: string; name: string }> {
  const { data } = await api.post('/api/folders', { name });
  return data;
}

export async function renameFolder(folderId: string, name: string): Promise<void> {
  await api.patch(`/api/folders/${folderId}`, { name });
}

export async function deleteFolder(folderId: string): Promise<void> {
  await api.delete(`/api/folders/${folderId}`);
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
  engine?: string; // "rules" (OCR + regex) or "gemini" (AI vision fallback)
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

/** Fetch a PNG thumbnail (page 1) of the stored receipt. */
export async function fetchInvoicePreview(invoiceId: string): Promise<Blob> {
  const { data } = await api.get<Blob>(`/api/invoices/${invoiceId}/preview`, {
    responseType: 'blob',
  });
  return data;
}

/** Optional filters shared by every export endpoint. */
export interface ExportFilters {
  status?: string | null;
  from?: string | null; // ISO date (yyyy-mm-dd)
  to?: string | null; // ISO date (yyyy-mm-dd)
  folderId?: string | null;
  ids?: string[] | null;
}

function exportQuery(filters: ExportFilters): string {
  const params = new URLSearchParams();
  if (filters.status) params.set('status', filters.status);
  if (filters.from) params.set('from', filters.from);
  if (filters.to) params.set('to', filters.to);
  if (filters.folderId) params.set('folder_id', filters.folderId);
  if (filters.ids?.length) params.set('ids', filters.ids.join(','));
  const qs = params.toString();
  return qs ? `?${qs}` : '';
}

/** Download a generated file blob and trigger a browser save. */
async function downloadBlob(path: string, filename: string): Promise<void> {
  const { data } = await api.get<Blob>(path, { responseType: 'blob' });
  const url = URL.createObjectURL(data);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

/** Download the CSV export via authenticated blob (no URL leaks). */
export async function downloadCsv(filters: ExportFilters = {}): Promise<void> {
  await downloadBlob(`/api/export/csv${exportQuery(filters)}`, 'invoxa_export.csv');
}

/** Download the export as Excel (XLSX) for Zoho Books / Excel import. */
export async function downloadXlsx(filters: ExportFilters = {}): Promise<void> {
  await downloadBlob(`/api/export/xlsx${exportQuery(filters)}`, 'invoxa_export.xlsx');
}

/** Download a Tally Prime XML voucher import file. */
export async function downloadTallyXml(filters: ExportFilters = {}): Promise<void> {
  await downloadBlob(`/api/export/tally-xml${exportQuery(filters)}`, 'invoxa_tally.xml');
}

/** Download a printable A4 statement PDF. */
export async function downloadStatementPdf(filters: ExportFilters = {}): Promise<void> {
  await downloadBlob(`/api/export/pdf${exportQuery(filters)}`, 'invoxa_statement.pdf');
}

export interface ExportPreview {
  rows: Record<string, string>[];
  count: number;
  total: number;
}

/** Ask the backend what an export with these filters would contain. */
export async function previewExport(filters: ExportFilters = {}): Promise<ExportPreview> {
  const { data } = await api.get<ExportPreview>(`/api/export/preview${exportQuery(filters)}`);
  return data;
}

/** Optional filters for the invoice list (search/status/date range). */
export interface InvoiceFilters {
  search?: string | null;
  status?: string | null;
  from?: string | null; // ISO date (yyyy-mm-dd)
  to?: string | null; // ISO date (yyyy-mm-dd)
}

/** Move an invoice into a folder (null = unfile). */
export async function setInvoiceFolder(invoiceId: string, folderId: string | null): Promise<void> {
  await api.patch(`/api/invoices/${invoiceId}/folder`, { folder_id: folderId });
}

/** Permanently delete an invoice, its file, and its review-queue entries. */
export async function deleteInvoice(invoiceId: string): Promise<void> {
  await api.delete(`/api/invoices/${invoiceId}`);
}

/** Move several invoices into one folder (null = unfile). */
export async function moveInvoicesToFolder(
  invoiceIds: string[],
  folderId: string | null,
): Promise<void> {
  await Promise.all(invoiceIds.map((id) => setInvoiceFolder(id, folderId)));
}

export async function fetchInvoices(
  folderId?: string | null,
  filters: InvoiceFilters = {},
): Promise<InvoiceSummary[]> {
  const params = new URLSearchParams();
  if (folderId) params.set('folder_id', folderId);
  if (filters.search) params.set('search', filters.search);
  if (filters.status) params.set('status', filters.status);
  if (filters.from) params.set('from', filters.from);
  if (filters.to) params.set('to', filters.to);
  const qs = params.toString();
  const { data } = await api.get<InvoiceSummary[]>(`/api/invoices${qs ? `?${qs}` : ''}`);
  return data;
}

export async function fetchInvoice(id: string): Promise<InvoiceDetail> {
  const { data } = await api.get<InvoiceDetail>(`/api/invoices/${id}`);
  return data;
}

export async function uploadInvoice(file: File, folderId?: string | null): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file, file.name);
  if (folderId) form.append('folder_id', folderId);
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
