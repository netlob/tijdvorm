import { writable } from "svelte/store";

function parseHash() {
  const raw = (location.hash || "#/").slice(1);
  const path = raw.startsWith("/") ? raw : `/${raw}`;
  const clean = path.replace(/\/+$/, "") || "/";

  if (clean === "/" || clean === "/home") return { name: "home" };
  if (clean === "/settings") return { name: "settings" };

  const eggPrefix = "/egg/";
  if (clean.startsWith(eggPrefix)) {
    const filename = decodeURIComponent(clean.slice(eggPrefix.length));
    return { name: "egg", filename };
  }

  return { name: "home" };
}

export const route = writable(parseHash());

export function goto(path) {
  const next = path.startsWith("/") ? path : `/${path}`;
  location.hash = `#${next}`;
}

window.addEventListener("hashchange", () => {
  route.set(parseHash());
});


