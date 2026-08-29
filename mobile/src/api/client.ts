import axios, { AxiosError, AxiosInstance, InternalAxiosRequestConfig } from 'axios';
import { API_BASE_URL, config } from '@/constants/config';
import { getToken } from '@/utils/storage';
import { ApiErrorResponse } from '@/types/api';

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: config.apiTimeoutMs,
  headers: {
    'Content-Type': 'application/json',
    Accept: 'application/json',
  },
});

// Request interceptor: attach Bearer token if present
apiClient.interceptors.request.use(
  async (requestConfig: InternalAxiosRequestConfig) => {
    try {
      const token = await getToken();
      if (token && requestConfig.headers) {
        requestConfig.headers.Authorization = `Bearer ${token}`;
      }
    } catch {
      // Continue request without token if secure store fails
    }
    return requestConfig;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor: standard error extraction
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError<ApiErrorResponse>) => {
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
