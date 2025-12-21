<script>
  let images = [];
  let loading = true;
  let error = "";
  let uploading = false;
  let selectedFile = null;
  let override = { filename: null, set_at: null };
  let settingOverride = false;
  let settings = { easter_egg_chance_denominator: 10 };
  let savingSettings = false;

  const cls = (...parts) => parts.filter(Boolean).join(" ");

  const ui = {
    card: "rounded-lg border border-border bg-card text-card-foreground shadow-sm",
    cardHeader: "px-4 pt-4 pb-2",
    cardTitle: "text-base font-semibold leading-none tracking-tight",
    cardDesc: "mt-1 text-sm text-muted-foreground",
    cardContent: "px-4 pb-4",
    button:
      "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:pointer-events-none disabled:opacity-50 h-9 px-3",
    buttonPrimary: "bg-primary text-primary-foreground hover:opacity-90",
    buttonSecondary: "bg-secondary text-secondary-foreground hover:opacity-90",
    buttonGhost: "hover:bg-accent hover:text-accent-foreground",
    buttonDestructive: "bg-destructive text-destructive-foreground hover:opacity-90",
    input:
      "flex h-9 w-full rounded-md border border-input bg-background px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
  };

  async function refresh() {
    loading = true;
    error = "";
    try {
      const [imagesRes, overrideRes, settingsRes] = await Promise.all([
        fetch("/api/images"),
        fetch("/api/override"),
        fetch("/api/settings")
      ]);
      if (!imagesRes.ok) throw new Error(await imagesRes.text());
      if (!overrideRes.ok) throw new Error(await overrideRes.text());
      if (!settingsRes.ok) throw new Error(await settingsRes.text());
      const data = await imagesRes.json();
      images = data.images ?? [];
      override = await overrideRes.json();
      settings = await settingsRes.json();
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      loading = false;
    }
  }

  async function upload() {
    if (!selectedFile) return;
    uploading = true;
    error = "";
    try {
      const fd = new FormData();
      fd.append("file", selectedFile);
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      if (!res.ok) throw new Error(await res.text());
      selectedFile = null;
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      uploading = false;
    }
  }

  async function setEnabled(filename, enabled) {
    error = "";
    try {
      const res = await fetch(`/api/images/${encodeURIComponent(filename)}/enabled`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled })
      });
      if (!res.ok) throw new Error(await res.text());
      images = images.map((img) => (img.filename === filename ? { ...img, enabled } : img));
    } catch (e) {
      error = e?.message ?? String(e);
      await refresh();
    }
  }

  async function setExplicit(filename, explicit) {
    error = "";
    try {
      const res = await fetch(`/api/images/${encodeURIComponent(filename)}/explicit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ explicit })
      });
      if (!res.ok) throw new Error(await res.text());
      images = images.map((img) => (img.filename === filename ? { ...img, explicit } : img));
    } catch (e) {
      error = e?.message ?? String(e);
      await refresh();
    }
  }

  async function removeImage(filename) {
    if (!confirm(`Delete ${filename}?`)) return;
    error = "";
    try {
      const res = await fetch(`/api/images/${encodeURIComponent(filename)}`, { method: "DELETE" });
      if (!res.ok) throw new Error(await res.text());
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
    }
  }

  async function setOverride(filenameOrNull) {
    settingOverride = true;
    error = "";
    try {
      const res = await fetch("/api/override", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filename: filenameOrNull })
      });
      if (!res.ok) throw new Error(await res.text());
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      settingOverride = false;
    }
  }

  async function saveSettings() {
    savingSettings = true;
    error = "";
    try {
      const denom = Number(settings.easter_egg_chance_denominator);
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ easter_egg_chance_denominator: denom })
      });
      if (!res.ok) throw new Error(await res.text());
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      savingSettings = false;
    }
  }

  refresh();
</script>

<main class="mx-auto w-full max-w-[960px] px-4 py-6 sm:px-6">
  <div class="flex flex-col gap-6">
    <header class="space-y-1">
      <div class="flex items-start justify-between gap-4">
        <div class="space-y-1">
          <h1 class="text-xl font-semibold tracking-tight sm:text-2xl">tijdvorm</h1>
          <p class="text-sm text-muted-foreground">Eastereggs manager (mobile-friendly)</p>
        </div>
        <button class={cls(ui.button, ui.buttonSecondary)} on:click={refresh} disabled={loading}>
          Refresh
        </button>
      </div>
    </header>

    {#if error}
      <div class={cls(ui.card, "border-destructive/50")}>
        <div class={ui.cardHeader}>
          <div class={ui.cardTitle}>Error</div>
          <div class={ui.cardDesc}>{error}</div>
        </div>
      </div>
    {/if}

    <div class="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <!-- Upload -->
      <section class={cls(ui.card, "lg:col-span-1")}>
        <div class={ui.cardHeader}>
          <div class={ui.cardTitle}>Upload</div>
          <div class={ui.cardDesc}>Add new images to the pool.</div>
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
            <p class="text-xs text-muted-foreground">
              Tip: upload multiple times. Images can be enabled/disabled below.
            </p>
          </div>
        </div>
      </section>

      <!-- Frequency -->
      <section class={cls(ui.card, "lg:col-span-1")}>
        <div class={ui.cardHeader}>
          <div class={ui.cardTitle}>Frequency</div>
          <div class={ui.cardDesc}>Controls how often an easter egg shows up.</div>
        </div>
        <div class={ui.cardContent}>
          <div class="flex flex-col gap-3">
            <label class="space-y-1">
              <div class="text-sm font-medium">Chance (1 in N)</div>
              <input
                class={ui.input}
                type="number"
                min="0"
                step="1"
                value={settings?.easter_egg_chance_denominator ?? 10}
                on:input={(e) =>
                  (settings = { ...settings, easter_egg_chance_denominator: Number(e.currentTarget.value) })}
              />
            </label>
            <button class={cls(ui.button, ui.buttonPrimary)} on:click={saveSettings} disabled={savingSettings}>
              {savingSettings ? "Saving…" : "Save"}
            </button>
            <p class="text-xs text-muted-foreground">0 = never. 1 = every minute. 10 = ~10% chance.</p>
          </div>
        </div>
      </section>

      <!-- Override -->
      <section class={cls(ui.card, "lg:col-span-1")}>
        <div class={ui.cardHeader}>
          <div class={ui.cardTitle}>Override</div>
          <div class={ui.cardDesc}>Force a specific image to show until cleared.</div>
        </div>
        <div class={ui.cardContent}>
          {#if override?.filename}
            <div class="flex items-center gap-3">
              <img
                class="h-12 w-12 shrink-0 rounded-md border border-border object-cover"
                alt={override.filename}
                src={override.url}
              />
              <div class="min-w-0 flex-1">
                <div class="truncate text-sm font-medium">{override.filename}</div>
                <div class="truncate text-xs text-muted-foreground">{override.set_at ? override.set_at : ""}</div>
              </div>
              <button
                class={cls(ui.button, ui.buttonSecondary)}
                on:click={() => setOverride(null)}
                disabled={settingOverride}
              >
                {settingOverride ? "Clearing…" : "Clear"}
              </button>
            </div>
          {:else}
            <div class="text-sm text-muted-foreground">No override set.</div>
          {/if}
        </div>
      </section>
    </div>

    <!-- Images -->
    <section class="space-y-3">
      <div class="flex items-center justify-between">
        <h2 class="text-base font-semibold">Images</h2>
        <div class="text-xs text-muted-foreground">{images.length} total</div>
      </div>

      {#if loading}
        <div class="text-sm text-muted-foreground">Loading…</div>
      {:else}
        <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {#each images as img (img.filename)}
            <article class={ui.card}>
              <div class="flex gap-3 p-3">
                <img
                  class="h-16 w-16 shrink-0 rounded-md border border-border object-cover"
                  alt={img.filename}
                  src={img.url}
                  loading="lazy"
                />
                <div class="min-w-0 flex-1">
                  <div class="truncate text-sm font-medium">{img.filename}</div>
                  <div class="truncate text-xs text-muted-foreground">
                    {img.uploaded_at ? `Uploaded: ${img.uploaded_at}` : "Existing file"}
                  </div>

                  <div class="mt-3 flex flex-wrap items-center gap-2">
                    <button
                      class={cls(ui.button, override?.filename === img.filename ? ui.buttonSecondary : ui.buttonPrimary)}
                      on:click={() => setOverride(img.filename)}
                      disabled={settingOverride}
                    >
                      {override?.filename === img.filename ? "Overriding" : "Override"}
                    </button>

                    <!-- Enabled switch -->
                    <label class="flex items-center gap-2 text-xs">
                      <span class="text-muted-foreground">Enabled</span>
                      <span class="relative inline-flex h-5 w-9 items-center">
                        <input
                          class="peer sr-only"
                          type="checkbox"
                          checked={img.enabled}
                          on:change={(e) => setEnabled(img.filename, e.currentTarget.checked)}
                        />
                        <span
                          class="h-5 w-9 rounded-full bg-muted transition-colors peer-checked:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-ring"
                        ></span>
                        <span
                          class="pointer-events-none absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-background shadow transition-transform peer-checked:translate-x-4"
                        ></span>
                      </span>
                    </label>

                    <!-- Explicit switch -->
                    <label class="flex items-center gap-2 text-xs">
                      <span class="text-muted-foreground">Explicit</span>
                      <span class="relative inline-flex h-5 w-9 items-center">
                        <input
                          class="peer sr-only"
                          type="checkbox"
                          checked={img.explicit}
                          on:change={(e) => setExplicit(img.filename, e.currentTarget.checked)}
                        />
                        <span
                          class="h-5 w-9 rounded-full bg-muted transition-colors peer-checked:bg-primary peer-focus-visible:ring-2 peer-focus-visible:ring-ring"
                        ></span>
                        <span
                          class="pointer-events-none absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-background shadow transition-transform peer-checked:translate-x-4"
                        ></span>
                      </span>
                    </label>

                    <button class={cls(ui.button, ui.buttonDestructive)} on:click={() => removeImage(img.filename)}>
                      Delete
                    </button>
                  </div>
                </div>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </section>
  </div>
</main>


