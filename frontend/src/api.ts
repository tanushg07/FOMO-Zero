import type { NoticeResult } from './types';

interface NoticeListResponse {
  items: NoticeResult[];
  limit: number;
  offset: number;
}

interface NoticeInput {
  text?: string;
  title?: string;
  file?: File;
}

async function parseResponse(response: Response): Promise<unknown> {
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const message = typeof payload === 'object' && payload !== null && 'message' in payload
      ? String(payload.message)
      : typeof payload === 'object' && payload !== null && 'detail' in payload
        ? String(payload.detail)
        : `Request failed (${response.status})`;
    throw new Error(message);
  }
  return payload;
}

export async function fetchNotices(): Promise<NoticeResult[]> {
  const payload = await parseResponse(await fetch('/api/notices?limit=100')) as NoticeListResponse;
  return payload.items;
}

export async function fetchNotice(noticeId: string): Promise<NoticeResult> {
  return parseResponse(await fetch(`/api/notices/${encodeURIComponent(noticeId)}`)) as Promise<NoticeResult>;
}

export async function createNotice(input: NoticeInput): Promise<NoticeResult> {
  let response: Response;
  if (input.file) {
    const form = new FormData();
    form.append('file', input.file);
    if (input.title?.trim()) form.append('title', input.title.trim());
    response = await fetch('/api/notices', { method: 'POST', body: form });
  } else {
    response = await fetch('/api/notices', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: input.title?.trim() || undefined, text: input.text?.trim() || '' }),
    });
  }
  return parseResponse(response) as Promise<NoticeResult>;
}

export async function extractNotice(noticeId: string): Promise<NoticeResult> {
  return parseResponse(await fetch(`/api/notices/${encodeURIComponent(noticeId)}/extract`, { method: 'POST' })) as Promise<NoticeResult>;
}
