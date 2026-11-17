import axios, { AxiosAdapter, AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { API_BASE_URL, config } from '@/constants/config';
import { assertSession, ensureSessionAccess, invalidateSession, sessionSnapshot, SessionAccessError } from './session';
import { ApiErrorResponse } from '@/types/api';

declare module 'axios' {
  interface AxiosRequestConfig {
    authMode?: 'none' | 'session';
  }
}

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: config.apiTimeoutMs,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

type SessionRequest = InternalAxiosRequestConfig & {
  sessionGeneration?: number; privateRequest?: boolean; authRetried?: boolean;
  sentToken?: string; originalAdapter?: AxiosAdapter;
};

apiClient.interceptors.request.use(
  (requestConfig: SessionRequest) => {
    const session = sessionSnapshot();
    // Keep synchronous binding: even requests waiting to dispatch belong to the
    // generation in which they were created, never the next account.
    requestConfig.sessionGeneration ??= session.generation;
    assertSession(requestConfig.sessionGeneration);
    requestConfig.privateRequest = requestConfig.authMode !== 'none';
    requestConfig.signal = session.signal;
    if (requestConfig.privateRequest) {
      if (!session.token) throw new axios.CanceledError('No authenticated session');
      requestConfig.headers.Authorization = `Bearer ${session.token}`;
      const generation = requestConfig.sessionGeneration;
      const adapter = requestConfig.originalAdapter ?? axios.getAdapter(requestConfig.adapter);
      requestConfig.originalAdapter = adapter;
      requestConfig.adapter = async config => {
        await ensureSessionAccess(generation);
        assertSession(generation);
        const token = sessionSnapshot().token;
        if (!token) throw new axios.CanceledError('No authenticated session');
        // Replace the header only after waiting for durable rotation/publication.
        config.headers.Authorization = `Bearer ${token}`;
        (config as SessionRequest).sentToken = token;
        return adapter(config);
      };
    } else {
      // Remove even inherited/default headers for credential-body endpoints.
      requestConfig.headers.delete('Authorization');
    }
    return requestConfig;
  },
  (error) => { throw error; },
  { synchronous: true },
);

function checkResponseSession(request?: SessionRequest) {
  if (request?.sessionGeneration !== undefined) assertSession(request.sessionGeneration);
}

function rejectAccessError(error: unknown): Promise<never> {
  if (error instanceof SessionAccessError && error.generation !== undefined) {
    assertSession(error.generation);
    if (error.terminal) invalidateSession(error.generation);
  }
  return Promise.reject(error);
}

// Response interceptor: standard error extraction
apiClient.interceptors.response.use(
  (response) => { checkResponseSession(response.config); return response; },
  (error: AxiosError<ApiErrorResponse>) => {
    if (error instanceof SessionAccessError) return rejectAccessError(error);
    const request = error.config as SessionRequest | undefined;
    checkResponseSession(request);
    if (axios.isCancel(error)) return Promise.reject(error);
    if (error.response?.status === 401 && request?.privateRequest && request.sessionGeneration !== undefined) {
      if (sessionSnapshot().refreshable && !request.authRetried) {
        const generation = request.sessionGeneration;
        return ensureSessionAccess(generation, request.sentToken).then(() => {
          assertSession(generation);
          // Authentication precedes backend financial handlers, but mutations
          // have no general idempotency contract. Only GET is replayed here.
          if (request.method?.toLowerCase() !== 'get') {
            throw new SessionAccessError(401, 'Your session was renewed. Review the action before trying again.');
          }
          request.authRetried = true;
          return apiClient.request(request);
        }, rejectAccessError);
      }
      invalidateSession(request.sessionGeneration);
    }
    if (error.response) {
      // Server responded with an error status code
      const errorData = error.response.data;
      const retryAfter = Object.entries(error.response.headers)
        .find(([name]) => name.toLowerCase() === 'retry-after')?.[1];
      let message = 'An unexpected error occurred';

      if (typeof errorData?.detail === 'string') {
        message = errorData.detail;
      } else if (Array.isArray(errorData?.detail) && errorData.detail.length > 0) {
        message = errorData.detail[0]?.msg || 'Validation failed';
      } else if (errorData?.message) {
        message = errorData.message;
      }

      return Promise.reject({
        statusCode: error.response.status,
        message,
        detail: errorData?.detail,
        retryAfter: retryAfter == null ? undefined : String(retryAfter),
      });
    }

    if (error.request) {
      // Network error or backend unreachable
      return Promise.reject({
        statusCode: 0,
        message: 'Unable to connect to the Dabbarha server. Please check your network.',
      });
    }

    return Promise.reject({
      statusCode: -1,
      message: error.message || 'Request failed to initialize.',
    });
  }
);
