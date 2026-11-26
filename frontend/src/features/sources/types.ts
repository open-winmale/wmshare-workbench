/** Sources 页的数据形状（与 `backend/workbench/tools/sources/handler.py` 对应）。 */

export interface Dataset {
  collection: string
  label: string
  stale_after_days: number
  expire_after_days: number
  topic: string
  ttl_s: number
  freshness: 'fresh' | 'stale' | 'expired' | 'unknown'
  age_days: number | null
  warning: string
}

export interface SourcesData {
  available: boolean
  count: number
  summary: Record<'fresh' | 'stale' | 'expired' | 'unknown', number>
  datasets: Dataset[]
  /** 新鲜度判定所用的参照日（今天） */
  reference?: string
  store: {
    ok: boolean
    version?: number
    tables?: number
    path?: string
    note?: string
  }
  credentials: { configured: boolean; source: string }
  note: string
}
