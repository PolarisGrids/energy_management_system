import { useState } from 'react'
import { Download, RotateCw } from 'lucide-react'
import { useSearchParams } from 'react-router-dom'
import { egsmDownloadsAPI } from '@/services/api'
import { useToast } from '@/components/ui/Toast'

// Kicks off a CSV download job via the mdms-analytics S3+SQS pipeline.
// The payload shape matches the avdhaan_v2 contract — reportName + all
// hierarchy + date-range filters from the URL search params.
export default function ReportDownloadButton({ reportName, extraParams = {}, title = 'Download CSV' }) {
  const [searchParams] = useSearchParams()
  const [loading, setLoading] = useState(false)
  const toast = useToast()

  const onClick = async () => {
    if (!reportName) return
    // Collect URL params — multi-value hierarchy keys stay as arrays.
    const payload = { reportName, ...extraParams }
    const MULTI = ['zone', 'circle', 'division', 'subdivision', 'substation_name', 'feeder_name', 'feeder_category', 'dtr_name']
    for (const key of MULTI) {
      const vals = searchParams.getAll(key)
      if (vals.length) payload[key] = vals
    }
    for (const [k, v] of searchParams.entries()) {
      if (!MULTI.includes(k) && !(k in payload)) payload[k] = v
    }
    setLoading(true)
    try {
      const res = await egsmDownloadsAPI.request(payload)
      if (res.data?.success) {
        toast.success('CSV queued', 'Check the MDMS Downloads console to fetch the file.')
      } else {
        toast.error('Download failed', res.data?.error?.message || 'Unknown error')
      }
    } catch (err) {
      toast.error('Download failed', err?.response?.data?.detail?.error?.message || err.message || 'Unknown error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      title={title}
      className="btn-secondary"
      style={{
        padding: '6px 10px', fontSize: 11, gap: 6,
        display: 'inline-flex', alignItems: 'center',
      }}
    >
      {loading ? <RotateCw size={12} className="animate-spin" /> : <Download size={12} />}
      CSV
    </button>
  )
}
