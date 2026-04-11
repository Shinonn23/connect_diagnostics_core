import { APIRequestContext, request } from '@playwright/test';

/** HTTP client ที่มี state สำหรับติดต่อกับ Frappe REST API */
export class FrappeClient {
  private baseUrl: string;
  private context!: APIRequestContext;

  /** สร้าง FrappeClient instance โดยเก็บ base URL สำหรับเรียก Frappe REST API */
  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
  }

  /** Login เข้าสู่ Frappe instance และเก็บ session context */
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

  /** ดึงรายการ documents จาก DocType ที่กำหนด พร้อมรองรับ fields, filters และ limit */
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

  /** นับจำนวน documents ที่ตรงกับ filters สำหรับ DocType */
  async getCount(doctype: string, filters: Record<string, any> = {}) {
    const params = new URLSearchParams();
    params.set('doctype', doctype);
    params.set('filters', JSON.stringify(filters));
    const res = await this.context.get(`/api/method/frappe.client.get_count?${params}`);
    const json = await res.json();
    return json.message || 0;
  }

  /** ดึง document เดียวตาม DocType และ name คืน null ถ้าไม่พบ */
  async getDoc(doctype: string, name: string) {
    const res = await this.context.get(
      `/api/resource/${doctype}/${encodeURIComponent(name)}`,
    );
    if (!res.ok()) return null;
    const json = await res.json();
    return json.data;
  }

  /** ปิดและคืนทรัพยากรของ HTTP request context */
  async dispose() {
    await this.context.dispose();
  }
}
