<script>
  import { onDestroy, onMount } from "svelte";
  import { cls, ui } from "../lib/ui.js";

  export let images = [];
  export let override = { filename: null };
  export let loading = false;
  export let error = "";
  export let livePreview = { updated_at: null, type: null, filename: null, url: null };

  export let onRefresh = async () => {};
  export let onOpenEgg = (filename) => {};
  export let onUpload = async (file) => {};

  let uploadOpen = false;
  let selectedFile = null;
  let uploading = false;
  let nowMs = Date.now();
  let tick = null;

  onMount(() => {
    tick = setInterval(() => {
      nowMs = Date.now();
    }, 1000);
  });

  onDestroy(() => {
    if (tick) clearInterval(tick);
  });

  function secondsSince(iso) {
    if (!iso) return null;
    const t = Date.parse(String(iso));
    if (!Number.isFinite(t)) return null;
    return Math.max(0, Math.floor((nowMs - t) / 1000));
  }

  async function upload() {
    if (!selectedFile) return;
    uploading = true;
    try {
      await onUpload(selectedFile);
      selectedFile = null;
      uploadOpen = false;
    } finally {
      uploading = false;
    }
  }
</script>

<div class="flex flex-col gap-4">
  {#if error}
    <div class={cls(ui.card, "border-destructive/50")}>
      <div class={ui.cardHeader}>
        <div class={ui.cardTitle}>Error</div>
        <div class={ui.cardDesc}>{error}</div>
      </div>
    </div>
  {/if}

  {#if livePreview?.url}
    <section class={ui.card}>
      <div class={ui.cardHeader}>
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class={ui.cardTitle}>Live preview</div>
            <div class={ui.cardDesc}>Last pushed to TV</div>
          </div>
        </div>
      </div>
      <div class={ui.cardContent}>
        <div class="flex items-stretch gap-3">
          <div class="w-1/4 max-w-[110px] shrink-0">
            <div class="aspect-[9/16] w-full overflow-hidden rounded-md border border-border bg-background">
              <img
                class="h-full w-full object-cover"
                style="transform: rotate(180deg);"
                alt="Live preview"
                src={livePreview.url}
              />
            </div>
          </div>

          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              {#if livePreview?.type}
                <span class="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{livePreview.type}</span>
              {/if}
              {#if livePreview?.updated_at}
                {@const s = secondsSince(livePreview.updated_at)}
                {#if s !== null}
                  <span class="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">{s}s ago</span>
                {/if}
              {/if}
            </div>

            {#if livePreview?.filename}
              <div class="mt-2 truncate text-sm font-medium">{livePreview.filename}</div>
            {/if}
            {#if livePreview?.updated_at}
              <div class="mt-1 truncate text-xs text-muted-foreground">{livePreview.updated_at}</div>
            {/if}

            {#if livePreview?.filename && (livePreview.type === "easteregg" || livePreview.type === "override")}
              <div class="mt-3">
                <button class={cls(ui.button, ui.buttonSecondary)} on:click={() => onOpenEgg(livePreview.filename)}>
                  Open {livePreview.type}
                </button>
              </div>
            {/if}
          </div>
        </div>
      </div>
    </section>
  {/if}

  <section class="space-y-3">
    <div class="flex items-center justify-between">
      <h2 class="text-base font-semibold">Eastereggs</h2>
      <div class="flex items-center gap-3">
        <div class="text-xs text-muted-foreground">{images.length} total</div>
        <button class={cls(ui.button, ui.buttonSecondary)} on:click={onRefresh} disabled={loading}>Refresh</button>
      </div>
    </div>

    {#if loading}
      <div class="text-sm text-muted-foreground">Loading…</div>
    {:else if images.length === 0}
      <div class="text-sm text-muted-foreground">No images yet. Upload one above.</div>
    {:else}
      <div class="grid grid-cols-2 gap-3">
        {#each images as img (img.filename)}
          <button
            type="button"
            class={cls(ui.card, "overflow-hidden p-0 text-left transition-colors hover:bg-accent/30")}
            on:click={() => onOpenEgg(img.filename)}
          >
            <!-- Images are 9:16 — keep a consistent 9:16 frame for a clean 2-up grid -->
            <div class="border-b border-border bg-muted/30">
              <div class="aspect-[9/16] w-full overflow-hidden rounded-md border border-border bg-background">
                <img
                  class="h-full w-full object-cover"
                  alt={img.filename}
                  src={img.url}
                  loading="lazy"
                />
              </div>
            </div>

            <div class="p-3">
              <div class="flex items-center justify-between gap-2">
                <div class="truncate text-sm font-medium">{img.filename}</div>
                <div class="shrink-0 text-muted-foreground">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
                    <path
                      d="M9 18l6-6-6-6"
                      stroke="currentColor"
                      stroke-width="2"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </div>
              </div>

              <div class="mt-2 flex flex-wrap items-center gap-2">
                {#if override?.filename === img.filename}
                  <span class="rounded-full bg-primary/15 px-2 py-0.5 text-[11px] text-primary">Override</span>
                {/if}
                {#if !img.enabled}
                  <span class="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">Disabled</span>
                {/if}
                {#if img.explicit}
                  <span class="rounded-full bg-muted px-2 py-0.5 text-[11px] text-muted-foreground">Explicit</span>
                {/if}
              </div>

              <div class="mt-2 truncate text-xs text-muted-foreground">
                {img.uploaded_at ? `Uploaded: ${img.uploaded_at}` : "Existing file"}
              </div>
            </div>
          </button>
        {/each}
      </div>
    {/if}
  </section>
</div>

<!-- Floating action button -->
<button
  type="button"
  class="fixed z-50 inline-flex h-14 w-14 items-center justify-center rounded-full bg-primary text-primary-foreground shadow-lg ring-1 ring-border/30 hover:opacity-90"
  style="right: 16px; bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom) + 16px);"
  aria-label="Upload"
  on:click={() => (uploadOpen = true)}
>
  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 5v14M5 12h14" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
  </svg>
</button>

<!-- Upload dialog (modal) -->
{#if uploadOpen}
  <div class="fixed inset-0 z-50 p-4" style="padding-top: calc(env(safe-area-inset-top) + 64px);">
    <!-- Backdrop as a real button => no a11y warnings, supports keyboard by default -->
    <button
      type="button"
      class="absolute inset-0 bg-black/60"
      aria-label="Close upload dialog"
      on:click={() => (uploadOpen = false)}
    ></button>

    <div class={cls(ui.card, "relative mx-auto w-full max-w-md")} role="dialog" aria-modal="true" aria-label="Upload easteregg">
      <div class={ui.cardHeader}>
        <div class="flex items-start justify-between gap-3">
          <div>
            <div class={ui.cardTitle}>Upload</div>
            <div class={ui.cardDesc}>Add a new image to the pool.</div>
          </div>
          <button class={cls(ui.button, ui.buttonGhost)} on:click={() => (uploadOpen = false)} aria-label="Close">
            ✕
          </button>
        </div>
      </div>
      <div class={ui.cardContent}>
        <div class="flex flex-col gap-3">
          <input
            class={ui.input}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            on:change={(e) => (selectedFile = e.currentTarget.files?.[0] ?? null)}
          />
          <button class={cls(ui.button, ui.buttonPrimary)} on:click={upload} disabled={!selectedFile || uploading}>
            {uploading ? "Uploading…" : "Upload"}
          </button>
          <button class={cls(ui.button, ui.buttonSecondary)} on:click={() => (uploadOpen = false)} disabled={uploading}>
            Cancel
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}


