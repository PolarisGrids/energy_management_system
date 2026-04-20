// GIS API client — wraps /api/v1/gis/* endpoints from spec 014-gis-postgis.
import axios from 'axios'

const api = axios.create({ baseURL: '/api/v1', timeout: 20000 })
api.interceptors.request.use((cfg) => {
  const token = localStorage.getItem('smoc_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

export const gisAPI = {
  layer: (name, { bbox, zoom } = {}) => {
    const params = {}
    if (bbox) params.bbox = bbox.join(',')
    if (typeof zoom === 'number') params.zoom = Math.round(zoom)
    return api.get(`/gis/layers/${name}`, { params }).then((r) => r.data)
  },
  layers: () => api.get('/gis/layers').then((r) => r.data),
}
