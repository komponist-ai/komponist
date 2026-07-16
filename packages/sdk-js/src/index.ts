export type EntityType = 'Decision' | 'Goal' | 'Constraint' | 'Project'

export interface Evidence {
  id: string
  source: string
  reference: string
  url?: string | null
  excerpt?: string | null
  source_date?: string | null
}

export interface ContextItem {
  id: string
  type: EntityType
  statement: string
  detail?: string | null
  confidence?: string | null
  evidence: Evidence[]
}

export interface ContextSearchResponse {
  items: ContextItem[]
  total: number
  query: string
}

export interface BrainInfo {
  organization_id: string
  confirmed: number
  pending_review: number
  confirmed_by_type: Partial<Record<EntityType, number>>
}

export interface Decision {
  id: string
  statement: string
  detail?: string | null
  confidence?: string | null
  confirmed_at?: string | null
  evidence: Evidence[]
  score?: number
}

export interface DecisionListResponse {
  decisions: Decision[]
  total: number
}

export interface KomponistError {
  message: string
  status: number
}

export type KomponistResult<T> =
  | { data: T; error: null }
  | { data: null; error: KomponistError }

export interface KomponistClientOptions {
  url: string
  apiKey: string
  fetch?: typeof globalThis.fetch
}

export interface ContextSearchOptions {
  types?: EntityType[]
  limit?: number
}

export interface DecisionListOptions {
  projectId?: string
  limit?: number
}

function boundedLimit(value: number | undefined, fallback: number, max: number): number {
  if (value === undefined) return fallback
  if (!Number.isInteger(value) || value < 1 || value > max) {
    throw new TypeError(`limit must be an integer between 1 and ${max}`)
  }
  return value
}

export class KomponistClient {
  readonly context: {
    search: (
      query: string,
      options?: ContextSearchOptions,
    ) => Promise<KomponistResult<ContextSearchResponse>>
  }

  readonly brain: {
    info: () => Promise<KomponistResult<BrainInfo>>
  }

  readonly decisions: {
    list: (
      options?: DecisionListOptions,
    ) => Promise<KomponistResult<DecisionListResponse>>
  }

  private readonly url: string
  private readonly apiKey: string
  private readonly fetcher: typeof globalThis.fetch

  constructor(options: KomponistClientOptions) {
    const url = options.url?.trim().replace(/\/+$/, '')
    const apiKey = options.apiKey?.trim()
    if (!url) throw new TypeError('Komponist url is required')
    if (!apiKey) throw new TypeError('Komponist apiKey is required')

    this.url = url
    this.apiKey = apiKey
    this.fetcher = options.fetch ?? globalThis.fetch
    if (!this.fetcher) throw new TypeError('A fetch implementation is required')

    this.context = {
      search: async (query, searchOptions = {}) => {
        const normalizedQuery = query.trim()
        if (!normalizedQuery) throw new TypeError('query is required')
        const params = new URLSearchParams({
          query: normalizedQuery,
          limit: String(boundedLimit(searchOptions.limit, 8, 20)),
        })
        for (const type of searchOptions.types ?? []) params.append('types', type)
        return this.request<ContextSearchResponse>(`/v1/context?${params}`)
      },
    }
    this.brain = { info: () => this.request<BrainInfo>('/v1/brain') }
    this.decisions = {
      list: async (decisionOptions = {}) => {
        const params = new URLSearchParams({
          limit: String(boundedLimit(decisionOptions.limit, 20, 100)),
        })
        if (decisionOptions.projectId) {
          params.set('project_id', decisionOptions.projectId)
        }
        return this.request<DecisionListResponse>(`/v1/decisions?${params}`)
      },
    }
  }

  private async request<T>(path: string): Promise<KomponistResult<T>> {
    try {
      const response = await this.fetcher(`${this.url}${path}`, {
        headers: {
          Accept: 'application/json',
          Authorization: `Bearer ${this.apiKey}`,
        },
      })
      const payload = await response.json().catch(() => null) as T | { detail?: string } | null
      if (!response.ok) {
        const detail = payload && typeof payload === 'object' && 'detail' in payload
          ? payload.detail
          : undefined
        return {
          data: null,
          error: {
            message: typeof detail === 'string' ? detail : `Komponist request failed (${response.status})`,
            status: response.status,
          },
        }
      }
      return { data: payload as T, error: null }
    } catch (cause) {
      return {
        data: null,
        error: {
          message: cause instanceof Error ? cause.message : 'Komponist request failed',
          status: 0,
        },
      }
    }
  }
}

export function createKomponistClient(options: KomponistClientOptions): KomponistClient {
  return new KomponistClient(options)
}
