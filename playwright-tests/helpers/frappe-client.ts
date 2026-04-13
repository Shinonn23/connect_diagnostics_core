import { APIRequestContext, request } from '@playwright/test';

export class FrappeClient {
  private baseUrl: string;
  private context!: APIRequestContext;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  async login(username: string, password: string) {
    this.context = await request.newContext({
      baseURL: this.baseUrl,
      ignoreHTTPSErrors: true,
    });
    const res = await this.context.post('/api/method/login', {
      form: { usr: username, pwd: password },
    });
    if (!res.ok()) throw new Error(`Login failed for ${this.baseUrl}: ${res.status()}`);
    return this;
  }

  async getDocList(
    doctype: string,
    fields: string[] = ['name'],
    filters: Record<string, any> = {},
    limit = 0,
  ) {
    const params = new URLSearchParams();
    params.set('doctype', doctype);
    params.set('fields', JSON.stringify(fields));
    params.set('filters', JSON.stringify(filters));
    params.set('limit_page_length', String(limit));
    const res = await this.context.get(`/api/method/frappe.client.get_list?${params}`);
    const json = await res.json();
    return json.message || [];
  }

  async getCount(doctype: string, filters: Record<string, any> = {}) {
    const params = new URLSearchParams();
    params.set('doctype', doctype);
    params.set('filters', JSON.stringify(filters));
    const res = await this.context.get(`/api/method/frappe.client.get_count?${params}`);
    const json = await res.json();
    return json.message || 0;
  }

  async getDoc(doctype: string, name: string) {
    const res = await this.context.get(
      `/api/resource/${doctype}/${encodeURIComponent(name)}`,
    );
    if (!res.ok()) return null;
    const json = await res.json();
    return json.data;
  }

  async dispose() {
    await this.context.dispose();
  }
}
