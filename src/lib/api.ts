// Use relative paths when served from same origin
const API_BASE_URL = import.meta.env.VITE_API_URL || (import.meta.env.PROD ? '' : 'http://localhost:8000');

let backendAvailable: boolean | null = null;

// Token storage keys
const ACCESS_TOKEN_KEY = 'accessToken';
const REFRESH_TOKEN_KEY = 'refreshToken';

// Token management functions
export function getAccessToken(): string | null {
  return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function setTokens(accessToken: string, refreshToken: string): void {
  localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
  localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
}

export function clearTokens(): void {
  localStorage.removeItem(ACCESS_TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
  // Also clear legacy userId if present
  localStorage.removeItem('userId');
}

export function isAuthenticated(): boolean {
  return !!getAccessToken();
}

// Token refresh logic
let refreshPromise: Promise<boolean> | null = null;

async function refreshAccessToken(): Promise<boolean> {
  // If already refreshing, wait for that promise
  if (refreshPromise) {
    return refreshPromise;
  }

  const refreshToken = getRefreshToken();
  if (!refreshToken) {
    return false;
  }

  refreshPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });

      if (!response.ok) {
        clearTokens();
        return false;
      }

      const data = await response.json();
      localStorage.setItem(ACCESS_TOKEN_KEY, data.access_token);
      return true;
    } catch {
      clearTokens();
      return false;
    } finally {
      refreshPromise = null;
    }
  })();

  return refreshPromise;
}

export async function checkBackendAvailable(): Promise<boolean> {
  if (backendAvailable !== null) return backendAvailable;

  try {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 2000);
    const response = await fetch(`${API_BASE_URL}/api/users/check/admin-exists`, {
      method: 'GET',
      signal: controller.signal,
    });
    clearTimeout(timeoutId);

    if (!response.ok) {
      backendAvailable = false;
      return false;
    }

    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      backendAvailable = false;
      return false;
    }

    const data = await response.json();
    backendAvailable = typeof data.admin_exists === 'boolean';
    return backendAvailable;
  } catch {
    backendAvailable = false;
    return false;
  }
}

export function isBackendAvailable(): boolean | null {
  return backendAvailable;
}

async function apiRequest<T>(
  endpoint: string,
  options: RequestInit = {},
  retry = true
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...options.headers as Record<string, string>,
  };

  // Add Authorization header if we have a token
  const accessToken = getAccessToken();
  if (accessToken) {
    headers['Authorization'] = `Bearer ${accessToken}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  // Handle 401 - try to refresh token
  if (response.status === 401 && retry) {
    const refreshed = await refreshAccessToken();
    if (refreshed) {
      // Retry the request with the new token
      return apiRequest<T>(endpoint, options, false);
    }
    // Refresh failed - redirect to login
    window.location.href = '/login';
    throw new Error('Session expired');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ message: 'Request failed' }));
    throw new Error(error.detail || error.message || `API request failed: ${response.status}`);
  }

  // Handle 204 No Content and other empty responses
  if (response.status === 204 || response.status === 205) {
    return undefined as T;
  }

  // Check if response has content
  const contentType = response.headers.get('content-type');
  if (!contentType || !contentType.includes('application/json')) {
    return undefined as T;
  }

  // Try to parse JSON, but handle empty body gracefully
  const text = await response.text();
  if (!text || text.trim() === '') {
    return undefined as T;
  }

  return JSON.parse(text);
}

// Hardcover API endpoints
export const hardcoverApi = {
  search: (query: string, limit: number = 20) =>
    apiRequest<{ books: any[] }>(`/api/hardcover/search?query=${encodeURIComponent(query)}&limit=${limit}`),

  searchGrouped: (
    query: string,
    limit: number = 10,
    options?: { cacheOnly?: boolean }
  ) => {
    const params = new URLSearchParams({
      query: query,
      limit: String(limit),
    });
    if (options?.cacheOnly) {
      params.set('cache_only', 'true');
    }
    return apiRequest<{ series: any[]; authors: any[]; books: any[] }>(
      `/api/hardcover/search-grouped?${params.toString()}`
    );
  },

  getDetails: (bookId: number, options?: { bypassCache?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.bypassCache) {
      params.set('bypass_cache', 'true');
    }
    const query = params.toString();
    return apiRequest<{ books_by_pk: any }>(
      `/api/hardcover/details/${bookId}${query ? `?${query}` : ''}`
    );
  },

  getEditions: (bookId: number, format?: 'ebook' | 'audiobook') => {
    const query = format ? `?format=${format}` : '';
    return apiRequest<{
      default_cover_edition_id: number | null;
      default_ebook_edition_id: number | null;
      default_audio_edition_id: number | null;
      editions: Array<{
        id: number;
        title?: string;
        score?: number;
        reading_format_id?: number;
        reading_format?: string;
        language?: string;
        language_code2?: string;
        publisher?: string;
        pages?: number;
        audio_seconds?: number;
        edition_format?: string;
        release_date?: string;
        release_year?: number;
      }>;
    }>(`/api/hardcover/editions/${bookId}${query}`);
  },

  getTrending: (limit: number = 20) =>
    apiRequest<{ books: any[] }>(`/api/hardcover/trending?limit=${limit}`),

  getPopular: (limit: number = 20) =>
    apiRequest<{ books: any[] }>(`/api/hardcover/popular?limit=${limit}`),

  getNewReleases: (limit: number = 20, minRatings: number = 5) => {
    const params = new URLSearchParams({
      limit: String(limit),
      min_ratings: String(minRatings),
    });
    return apiRequest<{ books: any[] }>(`/api/hardcover/new-releases?${params}`);
  },

  getSeries: (seriesId: number, options?: { bypassCache?: boolean }) => {
    const params = new URLSearchParams();
    if (options?.bypassCache) {
      params.set('bypass_cache', 'true');
    }
    const query = params.toString();
    return apiRequest<{ series_by_pk: any }>(
      `/api/hardcover/series/${seriesId}${query ? `?${query}` : ''}`
    );
  },

  rebuildSeries: (seriesId: number) =>
    apiRequest<{ series_by_pk: any }>(`/api/hardcover/series/${seriesId}/rebuild`, {
      method: 'POST',
    }),

  getSimilar: (bookId: number, limit: number = 10) =>
    apiRequest<{ books: any[] }>(`/api/hardcover/similar/${bookId}?limit=${limit}`),

  getBookPrompts: (bookId: number, promptLimit: number = 6, booksLimit: number = 30) =>
    apiRequest<{ prompt_summaries: any[] }>(
      `/api/hardcover/prompts/${bookId}?prompt_limit=${promptLimit}&books_limit=${booksLimit}`
    ),

  getPromptBySlug: (slug: string, limit: number = 1000, offset: number = 0, bypassCache: boolean = false) =>
    apiRequest<{ prompt: any }>(
      `/api/hardcover/prompt/${encodeURIComponent(slug)}?limit=${limit}&offset=${offset}&bypass_cache=${bypassCache}`
    ),

  getByAuthor: (bookId: number, limit: number = 10) =>
    apiRequest<{ books: any[] }>(`/api/hardcover/by-author/${bookId}?limit=${limit}`),

  getPopularSeries: (limit: number = 20, minTotalRatings: number = 500, offset: number = 0) => {
    const params = new URLSearchParams({
      limit: String(limit),
      min_total_ratings: String(minTotalRatings),
    });
    if (offset > 0) params.set('offset', String(offset));
    return apiRequest<{ series: any[] }>(`/api/hardcover/popular-series?${params}`);
  },

  getAuthor: (
    name: string,
    options?: {
      books_limit?: number;
      books_offset?: number;
      series_limit?: number;
      series_offset?: number;
    }
  ) => {
    const params = new URLSearchParams({ name });
    if (options?.books_limit != null) params.set('books_limit', String(options.books_limit));
    if (options?.books_offset != null) params.set('books_offset', String(options.books_offset));
    if (options?.series_limit != null) params.set('series_limit', String(options.series_limit));
    if (options?.series_offset != null) params.set('series_offset', String(options.series_offset));
    return apiRequest<{
      author: any;
      books: any[];
      books_total: number;
      series: any[];
      series_total: number;
    }>(`/api/hardcover/author?${params.toString()}`);
  },
};

// Books API endpoints
export const booksApi = {
  getAll: (skip: number = 0, limit: number = 100) =>
    apiRequest<Array<any>>(`/api/books/?skip=${skip}&limit=${limit}`),

  getById: (id: number) =>
    apiRequest<any>(`/api/books/${id}`),

  create: (book: any) =>
    apiRequest<any>('/api/books/', {
      method: 'POST',
      body: JSON.stringify(book),
    }),

  update: (id: number, book: any) =>
    apiRequest<any>(`/api/books/${id}`, {
      method: 'PUT',
      body: JSON.stringify(book),
    }),

  delete: (id: number) =>
    apiRequest<void>(`/api/books/${id}`, {
      method: 'DELETE',
    }),

  clearAvailability: (id: number, formatType: 'ebook' | 'audiobook') =>
    apiRequest<{ success: boolean; book_id: number; format_type: string; ebook_available: boolean; audiobook_available: boolean }>(
      `/api/books/${id}/availability/${formatType}`,
      { method: 'DELETE' }
    ),
};

// Requests API endpoints
export const requestsApi = {
  getAll: (skip: number = 0, limit: number = 100, status?: string, userId?: number) => {
    const params = new URLSearchParams({
      skip: String(skip),
      limit: String(limit),
    });
    if (status) params.append('status_filter', status);
    if (userId) params.append('user_id', String(userId));
    return apiRequest<Array<any>>(`/api/requests/?${params}`);
  },

  getById: (id: number) =>
    apiRequest<any>(`/api/requests/${id}`),

  create: (request: { book_id: number; format: string; notes?: string; edition_id?: number }) =>
    apiRequest<any>('/api/requests/', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  update: (id: number, update: { status?: string; admin_notes?: string }) =>
    apiRequest<any>(`/api/requests/${id}`, {
      method: 'PUT',
      body: JSON.stringify(update),
    }),

  delete: (id: number) =>
    apiRequest<void>(`/api/requests/${id}`, {
      method: 'DELETE',
    }),

  getByBook: (bookId: number) =>
    apiRequest<{ ebook: string | null; audiobook: string | null }>(`/api/requests/by-book/${bookId}`),

  getByHardcoverId: (hardcoverId: number) =>
    apiRequest<{
      ebook: string | null;
      audiobook: string | null;
      ebook_readarr_book_id: number | null;
      audiobook_readarr_book_id: number | null;
      book_id: number | null;
    }>(`/api/requests/by-hardcover/${hardcoverId}`),

  clearByHardcoverId: (hardcoverId: number, format?: 'ebook' | 'audiobook') =>
    apiRequest<{ message: string; deleted_count: number; formats: string[] }>(
      `/api/requests/by-hardcover/${hardcoverId}${format ? `?format=${format}` : ''}`,
      { method: 'DELETE' }
    ),

  getByHardcoverBatch: (hardcoverIds: number[]) =>
    apiRequest<{ results: Array<{ hardcover_id: number; ebook: string | null; audiobook: string | null }> }>(
      '/api/requests/by-hardcover/batch',
      {
        method: 'POST',
        body: JSON.stringify({ hardcover_ids: hardcoverIds }),
      }
    ),

  requestSeries: (
    seriesId: number,
    format: 'ebook' | 'audiobook' = 'ebook',
    originalOnly: boolean = false
  ) =>
    apiRequest<{
      series_id: number;
      format: string;
      requested_count: number;
      skipped_count: number;
      already_available: number;
      already_requested: number;
      total_books: number;
    }>(`/api/requests/series/${seriesId}?format=${format}${originalOnly ? '&original_only=true' : ''}`, {
      method: 'POST',
    }),

  clearSeries: (seriesId: number, format?: 'ebook' | 'audiobook') =>
    apiRequest<{
      message: string;
      series_id: number;
      deleted_count: number;
      formats: string[];
      affected_books: number;
    }>(`/api/requests/series/${seriesId}${format ? `?format=${format}` : ''}`, {
      method: 'DELETE',
    }),
};

// User type for the API
export interface ApiUser {
  id: number;
  email: string;
  username: string;
  full_name?: string;
  is_active: boolean;
  is_admin: boolean;
  can_request_ebook: boolean;
  can_request_audiobook: boolean;
  can_download: boolean;
  auto_approve_ebooks: boolean;
  auto_approve_audiobooks: boolean;
  created_at: string;
  updated_at?: string;
}

// Auth response types
export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

// Auth API endpoints
export const authApi = {
  login: async (username: string, password: string): Promise<LoginResponse> => {
    const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ detail: 'Login failed' }));
      throw new Error(error.detail || 'Invalid username or password');
    }

    const data = await response.json();
    setTokens(data.access_token, data.refresh_token);
    return data;
  },

  refresh: () =>
    apiRequest<{ access_token: string; token_type: string; expires_in: number }>(
      '/api/auth/refresh',
      {
        method: 'POST',
        body: JSON.stringify({ refresh_token: getRefreshToken() }),
      }
    ),

  logout: () => {
    clearTokens();
  },
};

// Users API endpoints
export const usersApi = {
  checkAdminExists: () =>
    apiRequest<{ admin_exists: boolean }>('/api/users/check/admin-exists'),

  getMe: () =>
    apiRequest<ApiUser>('/api/users/me'),

  changePassword: (currentPassword: string, newPassword: string) =>
    apiRequest<{ message: string }>('/api/users/me/password', {
      method: 'PUT',
      body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
    }),

  create: (user: { email: string; username: string; password: string; full_name?: string; is_admin?: boolean }) =>
    apiRequest<ApiUser>('/api/users/', {
      method: 'POST',
      body: JSON.stringify(user),
    }),

  getAll: (skip: number = 0, limit: number = 100) =>
    apiRequest<Array<ApiUser>>(`/api/users/?skip=${skip}&limit=${limit}`),

  getById: (id: number) =>
    apiRequest<ApiUser>(`/api/users/${id}`),

  update: (id: number, update: any) =>
    apiRequest<ApiUser>(`/api/users/${id}`, {
      method: 'PUT',
      body: JSON.stringify(update),
    }),

  delete: (id: number) =>
    apiRequest<void>(`/api/users/${id}`, {
      method: 'DELETE',
    }),
};

// Settings API endpoints
export const settingsApi = {
  getHardcoverToken: () =>
    apiRequest<{ hardcover_api_token: string | null; hardcover_api_token_source: string; has_hardcover_token: boolean }>('/api/settings/hardcover-token'),

  setHardcoverToken: (token: string) =>
    apiRequest<{ message: string }>('/api/settings/hardcover-token', {
      method: 'PUT',
      body: JSON.stringify({ hardcover_api_token: token }),
    }),

  getDownloadPaths: () =>
    apiRequest<{ ebook_download_path: string | null; audiobook_download_path: string | null }>('/api/settings/download-paths'),

  updateDownloadPaths: (paths: { ebook_download_path?: string; audiobook_download_path?: string }) =>
    apiRequest<{ message: string }>('/api/settings/download-paths', {
      method: 'PUT',
      body: JSON.stringify(paths),
    }),

  // Cache management (admin only)
  getCacheResources: () =>
    apiRequest<{ resources: Array<{ key: string; name: string; description: string }> }>('/api/settings/cache/resources'),

  clearCacheResource: (resource: string) =>
    apiRequest<{ message: string; deleted_count: number }>(`/api/settings/cache/clear/${resource}`, {
      method: 'POST',
    }),

  clearAllCache: () =>
    apiRequest<{ message: string; total_deleted: number; by_resource: Record<string, number> }>('/api/settings/cache/clear-all', {
      method: 'POST',
    }),

  debugCacheKeys: () =>
    apiRequest<{ total_keys: number; sample_keys: string[]; namespace: string }>('/api/settings/cache/debug'),
};

// Readarr API endpoints
export const readarrApi = {
  getAll: () =>
    apiRequest<Array<any>>('/api/readarr/'),

  getById: (id: number) =>
    apiRequest<any>(`/api/readarr/${id}`),

  create: (server: any) =>
    apiRequest<any>('/api/readarr/', {
      method: 'POST',
      body: JSON.stringify(server),
    }),

  update: (id: number, server: any) =>
    apiRequest<any>(`/api/readarr/${id}`, {
      method: 'PUT',
      body: JSON.stringify(server),
    }),

  delete: (id: number) =>
    apiRequest<void>(`/api/readarr/${id}`, {
      method: 'DELETE',
    }),

  testConnection: (config: { hostname: string; port: number; use_ssl: boolean; api_key: string; url_base?: string }) =>
    apiRequest<{
      success: boolean;
      error?: string;
      quality_profiles?: Array<{ id: number; name: string }>;
      root_folders?: Array<{ path: string; freeSpace?: number; totalSpace?: number }>;
      tags?: Array<{ id: number; label: string }>;
    }>('/api/readarr/test-connection', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  getConfiguredFormats: () =>
    apiRequest<{ ebook: boolean; audiobook: boolean }>('/api/readarr/configured-formats'),

  getAvailability: (hardcoverId: number) =>
    apiRequest<{ ebook: boolean; audiobook: boolean }>(`/api/readarr/availability/${hardcoverId}`),

  getAvailabilityBatch: (hardcoverIds: number[], isbnMap?: Record<number, string[]>) =>
    apiRequest<{ results: Array<{ hardcover_id: number; ebook: boolean; audiobook: boolean }> }>(
      '/api/readarr/availability/batch',
      {
        method: 'POST',
        body: JSON.stringify({ hardcover_ids: hardcoverIds, isbn_map: isbnMap }),
      }
    ),

  getAvailabilityByReadarrId: (readarrBookId: number, format: 'ebook' | 'audiobook') =>
    apiRequest<{ available: boolean; readarr_book_id: number; format: string }>(
      `/api/readarr/availability/readarr/${readarrBookId}?format=${format}`
    ),

  getManageLink: (hardcoverId: number, format?: 'ebook' | 'audiobook') =>
    apiRequest<{ url: string | null; format: string | null; readarr_book_id: number | null }>(
      `/api/readarr/manage-link/${hardcoverId}${format ? `?format=${format}` : ''}`
    ),
};

// Jobs API endpoints
export interface Job {
  name: string;
  type: string;
  interval_seconds: number;
  last_execution: string | null;
  next_execution: string | null;
  is_enabled?: boolean;
}

export interface IntervalOption {
  value: number;
  label: string;
}

export interface JobRunStatus {
  run_id: string;
  job_name: string;
  status: 'running' | 'completed' | 'failed';
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
  error: string | null;
}

export const jobsApi = {
  getAll: () =>
    apiRequest<Array<Job>>('/api/jobs/', {
      method: 'GET',
    }),

  getIntervals: () =>
    apiRequest<Array<IntervalOption>>('/api/jobs/intervals', {
      method: 'GET',
    }),

  update: (jobName: string, intervalSeconds: number) =>
    apiRequest<Job>(`/api/jobs/${jobName}`, {
      method: 'PUT',
      body: JSON.stringify({ interval_seconds: intervalSeconds }),
    }),

  run: (jobName: string) =>
    apiRequest<{
      message: string;
      job_name: string;
      run_id: string;
      triggered_at: string;
    }>(`/api/jobs/${jobName}/run`, {
      method: 'POST',
    }),

  getStatus: (runId: string) =>
    apiRequest<JobRunStatus>(`/api/jobs/status/${runId}`, {
      method: 'GET',
    }),
};

// Booklore API endpoints
export interface BookloreServer {
  id: number;
  name: string;
  url: string;
  username: string;
  is_default: boolean;
  created_at: string;
  updated_at?: string;
}

export interface BookloreTestResponse {
  success: boolean;
  error?: string;
  libraries?: Array<{ id: number; name: string }>;
}

export const bookloreApi = {
  getAll: () =>
    apiRequest<Array<BookloreServer>>('/api/booklore/'),

  getById: (id: number) =>
    apiRequest<BookloreServer>(`/api/booklore/${id}`),

  create: (server: { name: string; url: string; username: string; password: string; is_default?: boolean }) =>
    apiRequest<BookloreServer>('/api/booklore/', {
      method: 'POST',
      body: JSON.stringify(server),
    }),

  update: (id: number, server: { name?: string; url?: string; username?: string; password?: string; is_default?: boolean }) =>
    apiRequest<BookloreServer>(`/api/booklore/${id}`, {
      method: 'PUT',
      body: JSON.stringify(server),
    }),

  delete: (id: number) =>
    apiRequest<void>(`/api/booklore/${id}`, {
      method: 'DELETE',
    }),

  testConnection: (config: { url: string; username: string; password: string }) =>
    apiRequest<BookloreTestResponse>('/api/booklore/test', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  getBooks: (serverId: number) =>
    apiRequest<Array<any>>(`/api/booklore/${serverId}/books`),

  checkBook: (serverId: number, hardcoverId: number) =>
    apiRequest<{ available: boolean; book?: any }>(`/api/booklore/${serverId}/check/${hardcoverId}`),
};

// Download Settings API endpoints
export interface ProwlarrServer {
  id: number;
  name: string;
  host: string;
  port: number;
  use_ssl: boolean;
  api_key: string;
  url_base: string | null;
  enabled: boolean;
  is_default: boolean;
  indexer_ids: number[] | null;
}

export interface ProwlarrIndexer {
  id: number;
  name: string;
  protocol: string;
  privacy: string;
  enabled: boolean;
}

export interface DownloadClient {
  id: number;
  name: string;
  type: string;
  protocol: string;
  host: string;
  port: number;
  use_ssl: boolean;
  username: string | null;
  password: string;
  api_key: string | null;
  enabled: boolean;
  priority: number;
  category: string | null;
  ebook_category: string | null;
  audiobook_category: string | null;
  path_mappings_json: string | null;
}

export interface ProwlarrTestResponse {
  success: boolean;
  error?: string;
  indexers?: Array<any>;
  total_indexers?: number;
}

export interface DownloadClientTestResponse {
  success: boolean;
  error?: string;
  version?: string;
  api_version?: string;
}

export const downloadSettingsApi = {
  // Prowlarr endpoints
  getProwlarrServers: () =>
    apiRequest<Array<ProwlarrServer>>('/api/download-settings/prowlarr'),

  createProwlarrServer: (server: { name: string; host: string; port?: number; use_ssl?: boolean; api_key: string; url_base?: string; enabled?: boolean; is_default?: boolean; indexer_ids?: number[] }) =>
    apiRequest<ProwlarrServer>('/api/download-settings/prowlarr', {
      method: 'POST',
      body: JSON.stringify(server),
    }),

  updateProwlarrServer: (id: number, server: { name?: string; host?: string; port?: number; use_ssl?: boolean; api_key?: string; url_base?: string; enabled?: boolean; is_default?: boolean; indexer_ids?: number[] }) =>
    apiRequest<ProwlarrServer>(`/api/download-settings/prowlarr/${id}`, {
      method: 'PUT',
      body: JSON.stringify(server),
    }),

  deleteProwlarrServer: (id: number) =>
    apiRequest<{ message: string }>(`/api/download-settings/prowlarr/${id}`, {
      method: 'DELETE',
    }),

  testProwlarrConnection: (config: { host: string; port: number; use_ssl: boolean; api_key: string; url_base?: string }) =>
    apiRequest<ProwlarrTestResponse>('/api/download-settings/prowlarr/test', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  getProwlarrIndexers: (serverId: number) =>
    apiRequest<{ indexers: ProwlarrIndexer[] }>(`/api/download-settings/prowlarr/${serverId}/indexers`),

  // Download Client endpoints
  getDownloadClients: () =>
    apiRequest<Array<DownloadClient>>('/api/download-settings/download-clients'),

  createDownloadClient: (client: { name: string; type: string; protocol: string; host: string; port: number; use_ssl?: boolean; username?: string; password?: string; api_key?: string; enabled?: boolean; priority?: number; category?: string; ebook_category?: string; audiobook_category?: string; path_mappings_json?: string }) =>
    apiRequest<DownloadClient>('/api/download-settings/download-clients', {
      method: 'POST',
      body: JSON.stringify(client),
    }),

  updateDownloadClient: (id: number, client: { name?: string; type?: string; protocol?: string; host?: string; port?: number; use_ssl?: boolean; username?: string; password?: string; api_key?: string; enabled?: boolean; priority?: number; category?: string; ebook_category?: string; audiobook_category?: string; path_mappings_json?: string }) =>
    apiRequest<DownloadClient>(`/api/download-settings/download-clients/${id}`, {
      method: 'PUT',
      body: JSON.stringify(client),
    }),

  deleteDownloadClient: (id: number) =>
    apiRequest<{ message: string }>(`/api/download-settings/download-clients/${id}`, {
      method: 'DELETE',
    }),

  testDownloadClient: (config: { type: string; protocol: string; host: string; port: number; use_ssl: boolean; username?: string; password?: string; api_key?: string }) =>
    apiRequest<DownloadClientTestResponse>('/api/download-settings/download-clients/test', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
};

// Downloads API endpoints
export interface ReleaseInfo {
  title: string;
  download_url: string;
  protocol: string;
  indexer: string;
  size_bytes: number;
  seeders: number | null;
  format: string | null;
  language: string | null;
  quality_score: number;
  published_date: string | null;
  already_downloaded: boolean;
  info_url: string | null;
}

export interface SearchResponse {
  book_id: number;
  releases: ReleaseInfo[];
  total: number;
}

export interface DownloadResponse {
  task_id: number;
  status: string;
  message: string;
}

export interface DownloadTask {
  id: number;
  book_id: number;
  format: string;
  source: string;
  release_title: string;
  download_url: string;
  protocol: string;
  state: string;
  progress: number;
  download_path: string | null;
  import_status?: string;
  import_message?: string;
  imported_at?: string | null;
  created_at: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export const downloadsApi = {
  // Search for releases via Prowlarr
  searchReleases: (bookId: number, formatType: 'ebook' | 'audiobook') =>
    apiRequest<SearchResponse>(`/api/downloads/search/${bookId}?format_type=${formatType}`, {
      method: 'POST',
    }),

  // Manually download a specific release
  downloadRelease: (request: {
    book_id: number;
    format_type: string;
    download_url: string;
    protocol: string;
    release_title: string;
    indexer: string;
    size_bytes: number;
  }) =>
    apiRequest<DownloadResponse>('/api/downloads/download', {
      method: 'POST',
      body: JSON.stringify(request),
    }),

  // Automatically download the best release
  autoDownload: (bookId: number, formatType: 'ebook' | 'audiobook') =>
    apiRequest<DownloadResponse>(`/api/downloads/auto-download/${bookId}?format_type=${formatType}`, {
      method: 'POST',
    }),

  // Get download tasks
  getTasks: (skip?: number, limit?: number, state?: string) => {
    const params = new URLSearchParams();
    if (skip !== undefined) params.set('skip', String(skip));
    if (limit !== undefined) params.set('limit', String(limit));
    if (state) params.set('state', state);
    const query = params.toString();
    return apiRequest<DownloadTask[]>(`/api/downloads/tasks${query ? `?${query}` : ''}`);
  },

  // Manually import a download to the configured destination
  importDownload: (taskId: number) =>
    apiRequest<{ success: boolean; message: string; destination_path: string }>(
      `/api/downloads/import/${taskId}`,
      { method: 'POST' }
    ),

  // Delete a single download task
  deleteTask: (taskId: number) =>
    apiRequest<{ success: boolean; message: string }>(
      `/api/downloads/task/${taskId}`,
      { method: 'DELETE' }
    ),

  // Clear all eligible download tasks
  clearTasks: () =>
    apiRequest<{ success: boolean; message: string; deleted_count: number }>(
      '/api/downloads/tasks/clear',
      { method: 'DELETE' }
    ),
};
