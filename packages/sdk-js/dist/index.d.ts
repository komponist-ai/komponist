export type EntityType = 'Decision' | 'Goal' | 'Constraint' | 'Project';
export interface Evidence {
    id: string;
    source: string;
    reference: string;
    url?: string | null;
    excerpt?: string | null;
    source_date?: string | null;
}
export interface ContextItem {
    id: string;
    type: EntityType;
    statement: string;
    detail?: string | null;
    confidence?: string | null;
    evidence: Evidence[];
}
export interface ContextSearchResponse {
    items: ContextItem[];
    total: number;
    query: string;
}
export interface BrainInfo {
    organization_id: string;
    confirmed: number;
    pending_review: number;
    confirmed_by_type: Partial<Record<EntityType, number>>;
}
export interface Decision {
    id: string;
    statement: string;
    detail?: string | null;
    confidence?: string | null;
    confirmed_at?: string | null;
    evidence: Evidence[];
    score?: number;
}
export interface DecisionListResponse {
    decisions: Decision[];
    total: number;
}
export interface KomponistError {
    message: string;
    status: number;
}
export type KomponistResult<T> = {
    data: T;
    error: null;
} | {
    data: null;
    error: KomponistError;
};
export interface KomponistClientOptions {
    url: string;
    apiKey: string;
    fetch?: typeof globalThis.fetch;
}
export interface ContextSearchOptions {
    types?: EntityType[];
    limit?: number;
}
export interface DecisionListOptions {
    projectId?: string;
    limit?: number;
}
export declare class KomponistClient {
    readonly context: {
        search: (query: string, options?: ContextSearchOptions) => Promise<KomponistResult<ContextSearchResponse>>;
    };
    readonly brain: {
        info: () => Promise<KomponistResult<BrainInfo>>;
    };
    readonly decisions: {
        list: (options?: DecisionListOptions) => Promise<KomponistResult<DecisionListResponse>>;
    };
    private readonly url;
    private readonly apiKey;
    private readonly fetcher;
    constructor(options: KomponistClientOptions);
    private request;
}
export declare function createKomponistClient(options: KomponistClientOptions): KomponistClient;
