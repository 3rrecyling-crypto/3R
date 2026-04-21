const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/diesel';

async function apiFetch(endpoint: string, options?: RequestInit) {
  const url = `${API_BASE}${endpoint}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      ...(options?.headers || {}),
    },
    credentials: 'include',
  });
  if (!res.ok) {
    const error = await res.json().catch(() => ({ detail: 'Error de conexión' }));
    throw new Error(error.detail || JSON.stringify(error));
  }
  return res.json();
}

export const api = {
  // Dashboard
  getDashboard: (patioId?: number) =>
    apiFetch(`/api/dashboard/${patioId ? `?patio=${patioId}` : ''}`),

  // Patios
  getPatios: () => apiFetch('/api/patios/'),

  // Proveedores
  getProveedores: () => apiFetch('/api/proveedores/'),

  // Unidades
  getUnidades: (patioId?: number) =>
    apiFetch(`/api/unidades/${patioId ? `?patio=${patioId}` : ''}`),
  getUnidadesRendimiento: (patioId?: number) =>
    apiFetch(`/api/unidades/rendimiento/${patioId ? `?patio=${patioId}` : ''}`),

  // Cargas
  getCargas: (params?: Record<string, string>) => {
    const query = params ? '?' + new URLSearchParams(params).toString() : '';
    return apiFetch(`/api/cargas/${query}`);
  },
  crearCarga: (data: FormData) =>
    apiFetch('/api/cargas/crear/', { method: 'POST', body: data }),

  // Compras
  getCompras: (patioId?: number) =>
    apiFetch(`/api/compras/${patioId ? `?patio=${patioId}` : ''}`),
  crearCompra: (data: FormData) =>
    apiFetch('/api/compras/crear/', { method: 'POST', body: data }),

  // Ajustes
  getAjustes: (patioId?: number) =>
    apiFetch(`/api/ajustes/${patioId ? `?patio=${patioId}` : ''}`),
  crearAjuste: (data: Record<string, any>) =>
    apiFetch('/api/ajustes/crear/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  // Configuración Tótem
  getTotemConfig: (patioId: number) => apiFetch(`/api/totem/${patioId}/`),
  updateTotemConfig: (patioId: number, data: Record<string, any>) =>
    apiFetch(`/api/totem/${patioId}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
};

export default api;
