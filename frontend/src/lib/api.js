async function asText(res) {
  try {
    return await res.text();
  } catch {
    return "";
  }
}

function stripTrailingSlash(s) {
  return String(s || "").replace(/\/+$/, "");
}

// Configurable API host.
// Defaults to your homelab "production" node:
//   http://mini.netlob:8000
//
// Override in `frontend/.env.local`:
//   VITE_API_HOST=http://mini.netlob:8000
export const API_HOST = stripTrailingSlash(
  (import.meta.env.VITE_API_HOST && String(import.meta.env.VITE_API_HOST).trim()) || "http://mini.netlob:8000"
);

const API_BASE = `${API_HOST}/api`;

function withHost(url) {
  if (!url) return url;
  if (/^https?:\/\//i.test(url)) return url;
  if (url.startsWith("/")) return `${API_HOST}${url}`;
  return `${API_HOST}/${url}`;
}

export async function apiListImages() {
  const res = await fetch(`${API_BASE}/images`);
  if (!res.ok) throw new Error((await asText(res)) || "Failed to load images");
  const data = await res.json();
  const images = data.images ?? [];
  return images.map((img) => ({ ...img, url: withHost(img.url) }));
}

export async function apiGetOverride() {
  const res = await fetch(`${API_BASE}/override`);
  if (!res.ok) throw new Error((await asText(res)) || "Failed to load override");
  const ovr = await res.json();
  return ovr?.url ? { ...ovr, url: withHost(ovr.url) } : ovr;
}

export async function apiSetOverride(filenameOrNull) {
  const res = await fetch(`${API_BASE}/override`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filename: filenameOrNull })
  });
  if (!res.ok) throw new Error((await asText(res)) || "Failed to set override");
  return await res.json();
}

export async function apiUpload(file) {
  const fd = new FormData();
  fd.append("file", file);
  const res = await fetch(`${API_BASE}/upload`, { method: "POST", body: fd });
  if (!res.ok) throw new Error((await asText(res)) || "Failed to upload");
  return await res.json();
}

export async function apiSetEnabled(filename, enabled) {
  const res = await fetch(`${API_BASE}/images/${encodeURIComponent(filename)}/enabled`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled })
  });
  if (!res.ok) throw new Error((await asText(res)) || "Failed to set enabled");
  return await res.json();
}

export async function apiSetExplicit(filename, explicit) {
  const res = await fetch(`${API_BASE}/images/${encodeURIComponent(filename)}/explicit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ explicit })
  });
  if (!res.ok) throw new Error((await asText(res)) || "Failed to set explicit");
  return await res.json();
}

export async function apiDeleteImage(filename) {
  const res = await fetch(`${API_BASE}/images/${encodeURIComponent(filename)}`, { method: "DELETE" });
  if (!res.ok) throw new Error((await asText(res)) || "Failed to delete");
  return await res.json();
}

export async function apiGetSettings() {
  const res = await fetch(`${API_BASE}/settings`);
  if (!res.ok) throw new Error((await asText(res)) || "Failed to load settings");
  return await res.json();
}

export async function apiGetLivePreview() {
  const res = await fetch(`${API_BASE}/live-preview`);
  if (!res.ok) throw new Error((await asText(res)) || "Failed to load live preview");
  const data = await res.json();
  return data?.url ? { ...data, url: withHost(data.url) } : data;
}

export async function apiSetPriority(filename, priority) {
  const res = await fetch(`${API_BASE}/images/${encodeURIComponent(filename)}/priority`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ priority })
  });
  if (!res.ok) throw new Error((await asText(res)) || "Failed to set priority");
  return await res.json();
}

export async function apiSaveSettings({ easter_egg_chance_denominator }) {
  const denom = Number(easter_egg_chance_denominator);
  const res = await fetch(`${API_BASE}/settings`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ easter_egg_chance_denominator: denom })
  });
  if (!res.ok) throw new Error((await asText(res)) || "Failed to save settings");
  return await res.json();
}


