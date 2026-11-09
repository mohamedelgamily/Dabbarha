import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { API_BASE_URL, config } from '@/constants/config';
import { assertSession, invalidateSession, sessionSnapshot } from './session';
import { ApiErrorResponse } from '@/types/api';

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: config.apiTimeoutMs,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

type SessionRequest = InternalAxiosRequestConfig & { sessionGeneration?: number; privateRequest?: boolean };

apiClient.interceptors.request.use(
  (requestConfig: SessionRequest) => {
    const session = sessionSnapshot();
    requestConfig.sessionGeneration = session.generation;
    requestConfig.privateRequest = !['/auth/login', '/auth/register'].includes(requestConfig.url || '');
    requestConfig.signal = session.signal;
    if (requestConfig.privateRequest) {
      if (!session.token) throw new axios.CanceledError('No authenticated session');
      requestConfig.headers.Authorization = `Bearer ${session.token}`;
    }
    return requestConfig;
  },
  (error) => { throw error; },
  { synchronous: true },
);

function checkResponseSession(request?: SessionRequest) {
  if (request?.sessionGeneration !== undefined) assertSession(request.sessionGeneration);
}

// Response interceptor: standard error extraction
apiClient.interceptors.response.use(
  (response) => { checkResponseSession(response.config); return response; },
  (error: AxiosError<ApiErrorResponse>) => {
    const request = error.config as SessionRequest | undefined;
    checkResponseSession(request);
    if (axios.isCancel(error)) return Promise.reject(error);
    if (error.response?.status === 401 && request?.privateRequest && request.sessionGeneration !== undefined) {
      invalidateSession(request.sessionGeneration);
    }
    if (error.response) {
      // Server responded with an error status code
      const errorData = error.response.data;
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
