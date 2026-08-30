import axios from 'axios';

const baseURL = import.meta.env.VITE_API_BASE_URL ?? '';
export const apiBaseUrl = baseURL;

export const api = axios.create({
  baseURL,
  timeout: 120_000, // generous; backend cold-starts on Render free tier
});

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
  };
}

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>('/health');
  return data;
}

export async function fetchInvoices(): Promise<InvoiceSummary[]> {
  const { data } = await api.get<InvoiceSummary[]>('/api/invoices');
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
