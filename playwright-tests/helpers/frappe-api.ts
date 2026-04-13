import { APIRequestContext } from '@playwright/test';

const BASE = process.env.BASE_URL || 'https://dev.connectdiagnostics.nomeaparadigm.com';

export async function getDocList(
  request: APIRequestContext,
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
  const res = await request.get(`${BASE}/api/method/frappe.client.get_list?${params}`);
  const json = await res.json();
  return json.message || [];
}

export async function getDoc(
  request: APIRequestContext,
  doctype: string,
  name: string,
) {
  const res = await request.get(`${BASE}/api/resource/${doctype}/${encodeURIComponent(name)}`);
  const json = await res.json();
  return json.data;
}

export async function getCount(
  request: APIRequestContext,
  doctype: string,
  filters: Record<string, any> = {},
) {
  const params = new URLSearchParams();
  params.set('doctype', doctype);
  params.set('filters', JSON.stringify(filters));
  const res = await request.get(`${BASE}/api/method/frappe.client.get_count?${params}`);
  const json = await res.json();
  return json.message || 0;
}

export async function getInstalledApps(request: APIRequestContext): Promise<string[]> {
  try {
    const res = await request.get(`${BASE}/api/method/frappe.client.get_list`, {
      params: {
        doctype: 'Installed Application',
        fields: JSON.stringify(['app_name', 'app_version']),
        limit_page_length: '0',
      },
    });
    const json = await res.json();
    if (json.message && json.message.length > 0) {
      return json.message;
    }
  } catch {}
  const modules = await getDocList(request, 'Module Def', ['name'], {}, 0);
  return modules.map((m: any) => m.name);
}

export function checkRequiredFields(
  doc: Record<string, any>,
  fields: string[],
): { field: string; value: any }[] {
  const missing: { field: string; value: any }[] = [];
  for (const f of fields) {
    const val = doc[f];
    if (val === null || val === undefined || val === '' || val === 0) {
      missing.push({ field: f, value: val });
    }
  }
  return missing;
}
