import type {
  CompanyPage,
  GraphResponse,
  RiskResponse,
} from "../types/intelligence";

const base = (import.meta.env.VITE_API_URL || "/api/v1").replace(/\/$/, "");

export async function request<T>(
  path: string,
  signal?: AbortSignal,
): Promise<T> {
  const response = await fetch(`${base}${path}`, { signal });
  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new Error(
      payload?.error?.message || `Request failed (${response.status})`,
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  companies: (
    search: string,
    industry: string,
    page: number,
    signal?: AbortSignal,
  ) =>
    request<CompanyPage>(
      `/companies?${new URLSearchParams({ search, industry, page: String(page), page_size: "12" })}`,
      signal,
    ),
  graph: (id: string, depth: number, direction: string, signal?: AbortSignal) =>
    request<GraphResponse>(
      `/graph/${id}?depth=${depth}&direction=${direction}`,
      signal,
    ),
  risk: (id: string, signal?: AbortSignal) =>
    request<RiskResponse>(`/risk/${id}`, signal),
};
