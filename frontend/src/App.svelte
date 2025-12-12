<script>
  let images = [];
  let loading = true;
  let error = "";
  let uploading = false;
  let selectedFile = null;

  async function refresh() {
    loading = true;
    error = "";
    try {
      const res = await fetch("/api/images");
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      images = data.images ?? [];
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

  refresh();
</script>

<main>
  <header>
    <hgroup>
      <h1>tijdvorm – eastereggs</h1>
      <p class="muted">Upload images + enable/disable which ones can show up (1 in 10 chance each minute).</p>
    </hgroup>
  </header>

  {#if error}
    <article class="card" style="border-color: var(--pico-del-color);">
      <strong>Error</strong>
      <div class="muted">{error}</div>
    </article>
  {/if}

  <article class="card">
    <h3>Upload</h3>
    <div class="row" style="align-items: flex-end;">
      <label style="flex: 1;">
        Pick image
        <input
          type="file"
          accept="image/png,image/jpeg,image/webp"
          on:change={(e) => (selectedFile = e.currentTarget.files?.[0] ?? null)}
        />
      </label>
      <button on:click={upload} disabled={!selectedFile || uploading}>
        {uploading ? "Uploading…" : "Upload"}
      </button>
      <button class="secondary" on:click={refresh} disabled={loading}>
        Refresh
      </button>
    </div>
    <small class="muted">Tip: add more images by uploading multiple times.</small>
  </article>

  {#if loading}
    <p class="muted">Loading…</p>
  {:else}
    <div class="grid">
      {#each images as img (img.filename)}
        <article class="card">
          <div class="row" style="align-items: flex-start;">
            <div class="row" style="gap: 0.75rem; align-items: flex-start;">
              <img class="thumb" alt={img.filename} src={img.url} />
              <div>
                <strong>{img.filename}</strong>
                <div class="muted">
                  {img.uploaded_at ? `Uploaded: ${img.uploaded_at}` : "Existing file"}
                </div>
              </div>
            </div>

            <div style="display: flex; gap: 0.5rem; align-items: center;">
              <label>
                <input
                  type="checkbox"
                  role="switch"
                  checked={img.enabled}
                  on:change={(e) => setEnabled(img.filename, e.currentTarget.checked)}
                />
                Enabled
              </label>
              <button class="secondary" on:click={() => removeImage(img.filename)}>Delete</button>
            </div>
          </div>
        </article>
      {/each}
    </div>
  {/if}
</main>


