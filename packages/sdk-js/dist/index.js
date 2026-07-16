function boundedLimit(value, fallback, max) {
    if (value === undefined)
        return fallback;
    if (!Number.isInteger(value) || value < 1 || value > max) {
        throw new TypeError(`limit must be an integer between 1 and ${max}`);
    }
    return value;
}
export class KomponistClient {
    context;
    brain;
    decisions;
    url;
    apiKey;
    fetcher;
    constructor(options) {
        const url = options.url?.trim().replace(/\/+$/, '');
        const apiKey = options.apiKey?.trim();
        if (!url)
            throw new TypeError('Komponist url is required');
        if (!apiKey)
            throw new TypeError('Komponist apiKey is required');
        this.url = url;
        this.apiKey = apiKey;
        this.fetcher = options.fetch ?? globalThis.fetch;
        if (!this.fetcher)
            throw new TypeError('A fetch implementation is required');
        this.context = {
            search: async (query, searchOptions = {}) => {
                const normalizedQuery = query.trim();
                if (!normalizedQuery)
                    throw new TypeError('query is required');
                const params = new URLSearchParams({
                    query: normalizedQuery,
                    limit: String(boundedLimit(searchOptions.limit, 8, 20)),
                });
                for (const type of searchOptions.types ?? [])
                    params.append('types', type);
                return this.request(`/v1/context?${params}`);
            },
        };
        this.brain = { info: () => this.request('/v1/brain') };
        this.decisions = {
            list: async (decisionOptions = {}) => {
                const params = new URLSearchParams({
                    limit: String(boundedLimit(decisionOptions.limit, 20, 100)),
                });
                if (decisionOptions.projectId) {
                    params.set('project_id', decisionOptions.projectId);
                }
                return this.request(`/v1/decisions?${params}`);
            },
        };
    }
    async request(path) {
        try {
            const response = await this.fetcher(`${this.url}${path}`, {
                headers: {
                    Accept: 'application/json',
                    Authorization: `Bearer ${this.apiKey}`,
                },
            });
            const payload = await response.json().catch(() => null);
            if (!response.ok) {
                const detail = payload && typeof payload === 'object' && 'detail' in payload
                    ? payload.detail
                    : undefined;
                return {
                    data: null,
                    error: {
                        message: typeof detail === 'string' ? detail : `Komponist request failed (${response.status})`,
                        status: response.status,
                    },
                };
            }
            return { data: payload, error: null };
        }
        catch (cause) {
            return {
                data: null,
                error: {
                    message: cause instanceof Error ? cause.message : 'Komponist request failed',
                    status: 0,
                },
            };
        }
    }
}
export function createKomponistClient(options) {
    return new KomponistClient(options);
}
