import type { APIRequestContext, Page } from '@playwright/test';

export interface FrappeField {
  fieldname: string;
  label?: string;
  fieldtype?: string;
  options?: string;
}

export interface FrappeMeta {
  name: string;
  title_field?: string;
  fields: FrappeField[];
}

interface JsonResponse<T> {
  data?: T;
  message?: T;
  exc?: string;
  exception?: string;
}

interface GetDoctypeResponse {
  docs?: Array<{
    name: string;
    title_field?: string;
    fields?: FrappeField[];
  }>;
}

export class FrappeClient {
  private readonly metaCache = new Map<string, Promise<FrappeMeta>>();
  private readonly maxRequestAttempts = 3;

  constructor(
    private readonly request: APIRequestContext,
    private readonly baseURL: string,
  ) {}

  async getMeta(doctype: string): Promise<FrappeMeta> {
    if (!this.metaCache.has(doctype)) {
      this.metaCache.set(
        doctype,
        this.getDoctypeMeta(doctype),
      );
    }

    return this.metaCache.get(doctype)!;
  }

  async listAll(
    doctype: string,
    fields: string[],
    filters?: Record<string, string | number | boolean>,
  ): Promise<Record<string, unknown>[]> {
    const uniqueFields = [...new Set(['name', ...fields])];
    const pageLength = 500;
    const output: Record<string, unknown>[] = [];
    const query = new URLSearchParams({
      fields: JSON.stringify(uniqueFields),
      limit_page_length: String(pageLength),
      order_by: 'modified asc',
    });

    if (filters && Object.keys(filters).length > 0) {
      query.set('filters', JSON.stringify(filters));
    }

    for (let start = 0; ; start += pageLength) {
      query.set('limit_start', String(start));
      const response = await this.getJson<Record<string, unknown>[]>(
        `/api/resource/${encodeURIComponent(doctype)}?${query.toString()}`,
      );
      const rows = response.data ?? response.message ?? [];
      output.push(...rows);
      if (rows.length < pageLength) {
        return output;
      }
    }
  }

  async getDoc(
    doctype: string,
    name: string,
  ): Promise<Record<string, unknown>> {
    const response = await this.getJson<Record<string, unknown>>(
      `/api/resource/${encodeURIComponent(doctype)}/${encodeURIComponent(name)}`,
    );
    return response.data ?? response.message ?? {};
  }

  private async getDoctypeMeta(doctype: string): Promise<FrappeMeta> {
    const response = (await this.getJson<GetDoctypeResponse>(
      `/api/method/frappe.desk.form.load.getdoctype?doctype=${encodeURIComponent(doctype)}`,
    )) as JsonResponse<GetDoctypeResponse> & GetDoctypeResponse;
    const doc = response.docs?.[0];
    if (!doc) {
      throw new Error(`Doctype metadata for "${doctype}" returned no docs.`);
    }

    return {
      name: doc.name,
      title_field: doc.title_field,
      fields: doc.fields ?? [],
    };
  }

  private async getJson<T>(relativeUrl: string): Promise<JsonResponse<T>> {
    let lastError: Error | undefined;

    for (let attempt = 1; attempt <= this.maxRequestAttempts; attempt += 1) {
      try {
        const response = await this.request.get(this.buildUrl(relativeUrl), {
          headers: {
            Accept: 'application/json',
          },
        });

        if (!response.ok()) {
          const status = response.status();
          const error = new Error(
            `GET ${relativeUrl} failed with ${status} ${response.statusText()}`,
          );
          if (attempt < this.maxRequestAttempts && isRetriableStatus(status)) {
            lastError = error;
            await delay(attempt * 1_000);
            continue;
          }
          throw error;
        }

        const payload = (await response.json()) as JsonResponse<T> & GetDoctypeResponse;
        if (payload.exc || payload.exception) {
          throw new Error(
            `Frappe returned an exception for ${relativeUrl}: ${payload.exc ?? payload.exception}`,
          );
        }
        return payload;
      } catch (error) {
        const normalizedError =
          error instanceof Error ? error : new Error(String(error));
        if (
          attempt < this.maxRequestAttempts &&
          isRetriableRequestError(normalizedError)
        ) {
          lastError = normalizedError;
          await delay(attempt * 1_000);
          continue;
        }
        throw normalizedError;
      }
    }

    throw lastError ?? new Error(`GET ${relativeUrl} failed after retries.`);
  }

  private buildUrl(relativeUrl: string): string {
    return new URL(relativeUrl, this.baseURL).toString();
  }
}

function isRetriableStatus(status: number): boolean {
  return status === 408 || status === 429 || status >= 500;
}

function isRetriableRequestError(error: Error): boolean {
  const message = error.message.toUpperCase();
  return [
    'ETIMEDOUT',
    'ECONNRESET',
    'EAI_AGAIN',
    'ECONNREFUSED',
    'SOCKET HANG UP',
  ].some((pattern) => message.includes(pattern));
}

async function delay(ms: number): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, ms));
}

export async function loginToFrappe(page: Page, username: string, password: string) {
  await page.goto('/login');

  const emailInput = page.locator(
    '#login_email, input[name="login_email"], input[type="email"], input[type="text"]',
  );
  const passwordInput = page.locator(
    '#login_password, input[name="login_password"], input[type="password"]',
  );
  const loginButton = page.locator(
    'button:has-text("Login"), .btn-login, [type="submit"]',
  );

  await emailInput.first().fill(username);
  await passwordInput.first().fill(password);

  await Promise.all([
    page.waitForURL(/\/app\//, { timeout: 30_000 }),
    loginButton.first().click(),
  ]);

  if (page.url().includes('/login')) {
    const errorMessage = await page
      .locator('.msgprint, .alert, .indicator, .page-card-body .invalid-feedback')
      .allTextContents()
      .catch(() => []);
    throw new Error(
      `Login did not leave the login page. ${errorMessage.join(' ').trim()}`.trim(),
    );
  }
}
