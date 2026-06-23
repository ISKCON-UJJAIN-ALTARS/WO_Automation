// src/services/api.js
import axios from 'axios';

const BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: BASE_URL,
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
});

apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    const message =
      error?.response?.data?.message || error?.message || 'Unexpected network error';
    return Promise.reject(new Error(message));
  }
);

/**
 * Fetch the list of available templates from the backend.
 * Falls back gracefully — callers should prefer local metadata
 * (src/data/templates.js) for UI rendering and use this only to
 * confirm backend availability / versioning.
 */
export async function fetchTemplates() {
  const { data } = await apiClient.get('/templates');
  return data;
}

/**
 * Generate a work order drawing.
 * @param {string} template - template id, e.g. "4dome_ceiling"
 * @param {Record<string, number>} inputs - merged field values
 */
export async function generateWorkOrder(template, inputs) {
  const { data } = await apiClient.post('/generate', { template, inputs });
  return data;
}

export function resolveImageUrl(imagePath) {
  if (!imagePath) return null;
  if (imagePath.startsWith('http')) return imagePath;
  return `${BASE_URL}${imagePath}`;
}
