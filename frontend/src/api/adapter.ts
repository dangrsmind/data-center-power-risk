/**
 * API Adapter Layer
 *
 * To switch from mock data to the real backend:
 * 1. Set USE_MOCK = false (or set VITE_USE_MOCK=false in your .env)
 * 2. Set BASE_URL to your backend URL (or set VITE_API_BASE_URL in .env)
 *
 * All components import from this file only — never from mock.ts directly.
 */

import type {
  ProjectListItem,
  ProjectDetail,
  TimelineEvent,
} from "./types";
import {
  MOCK_PROJECTS,
  MOCK_PROJECT_DETAILS,
  MOCK_TIMELINES,
} from "./mock";

const USE_MOCK =
  import.meta.env.VITE_USE_MOCK !== "false";

const BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? "http://localhost:5000";

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`API error ${res.status} for ${path}`);
  }
  return res.json() as Promise<T>;
}

function delay(ms = 120): Promise<void> {
  return new Promise((r) => setTimeout(r, ms));
}

export async function getProjects(): Promise<ProjectListItem[]> {
  if (USE_MOCK) {
    await delay();
    return MOCK_PROJECTS;
  }
  return fetchJson<ProjectListItem[]>("/projects");
}

export async function getProject(id: string): Promise<ProjectDetail> {
  if (USE_MOCK) {
    await delay();
    const detail = MOCK_PROJECT_DETAILS[id];
    if (!detail) throw new Error(`Project ${id} not found in mock data`);
    return detail;
  }
  return fetchJson<ProjectDetail>(`/projects/${id}`);
}

export async function getTimeline(id: string): Promise<TimelineEvent[]> {
  if (USE_MOCK) {
    await delay();
    return MOCK_TIMELINES[id] ?? [];
  }
  return fetchJson<TimelineEvent[]>(`/projects/${id}/timeline`);
}
