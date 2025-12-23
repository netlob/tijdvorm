<script>
  import { cls, ui } from "../lib/ui.js";

  export let image = null;
  export let override = { filename: null };
  export let busy = false;
  export let error = "";

  export let onBack = () => {};
  export let onRefresh = async () => {};
  export let onSetOverride = async (filenameOrNull) => {};
  export let onSetEnabled = async (filename, enabled) => {};
  export let onSetExplicit = async (filename, explicit) => {};
  export let onSetPriority = async (filename, priority) => {};
  export let onDelete = async (filename) => {};
  export let onDeleted = () => {};

  let deleting = false;

  async function remove() {
    if (!image) return;
    if (!confirm(`Delete ${image.filename}?`)) return;
    deleting = true;
    try {
      await onDelete(image.filename);
      onDeleted();
    } finally {
      deleting = false;
    }
  }
</script>

<div class="flex flex-col gap-4">
  <div class="flex items-center justify-between gap-3">
    <button class={cls(ui.button, ui.buttonGhost)} on:click={onBack}>
      <span class="mr-1 inline-block" aria-hidden="true">←</span>
      Back
    </button>
    <button class={cls(ui.button, ui.buttonSecondary)} on:click={onRefresh} disabled={busy}>Refresh</button>
  </div>

  {#if error}
    <div class={cls(ui.card, "border-destructive/50")}>
      <div class={ui.cardHeader}>
        <div class={ui.cardTitle}>Error</div>
        <div class={ui.cardDesc}>{error}</div>
      </div>
    </div>
  {/if}

  {#if !image}
    <div class={ui.card}>
      <div class={ui.cardHeader}>
        <div class={ui.cardTitle}>Not found</div>
        <div class={ui.cardDesc}>This easteregg doesn’t exist (anymore).</div>
      </div>
      <div class={ui.cardContent}>
        <button class={cls(ui.button, ui.buttonPrimary)} on:click={onBack}>Go back</button>
      </div>
    </div>
  {:else}
    <section class={ui.card}>
      <div class={ui.cardHeader}>
        <div class={ui.cardTitle}>{image.filename}</div>
        <div class={ui.cardDesc}>{image.uploaded_at ? `Uploaded: ${image.uploaded_at}` : "Existing file"}</div>
      </div>
      <div class={ui.cardContent}>
        <img
          class="w-full rounded-lg border border-border bg-muted object-contain"
          style="max-height: min(48vh, 420px);"
          alt={image.filename}
          src={image.url}
        />
      </div>
    </section>

    <section class={ui.card}>
      <div class={ui.cardHeader}>
        <div class={ui.cardTitle}>Controls</div>
        <div class={ui.cardDesc}>Override, flags, and deletion live here.</div>
      </div>
      <div class={ui.cardContent}>
        <div class="flex flex-col gap-4">
          <div class="flex flex-wrap items-center gap-2">
            {#if override?.filename === image.filename}
              <button class={cls(ui.button, ui.buttonSecondary)} on:click={() => onSetOverride(null)} disabled={busy}>
                Clear override
              </button>
            {:else}
              <button class={cls(ui.button, ui.buttonPrimary)} on:click={() => onSetOverride(image.filename)} disabled={busy}>
                Set override
              </button>
            {/if}
          </div>

          <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <label class="flex items-center justify-between gap-3 rounded-md border border-border bg-background/40 px-3 py-2">
              <div>
                <div class="text-sm font-medium">Enabled</div>
                <div class="text-xs text-muted-foreground">If off, it won’t show up.</div>
              </div>
              <input
                type="checkbox"
                checked={!!image.enabled}
                on:change={(e) => onSetEnabled(image.filename, e.currentTarget.checked)}
              />
            </label>

            <label class="flex items-center justify-between gap-3 rounded-md border border-border bg-background/40 px-3 py-2">
              <div>
                <div class="text-sm font-medium">Explicit</div>
                <div class="text-xs text-muted-foreground">Marks NSFW-ish items.</div>
              </div>
              <input
                type="checkbox"
                checked={!!image.explicit}
                on:change={(e) => onSetExplicit(image.filename, e.currentTarget.checked)}
              />
            </label>
          </div>

          <div class="rounded-md border border-border bg-background/40 px-3 py-3">
            <div class="flex items-start justify-between gap-3">
              <div>
                <div class="text-sm font-medium">Priority</div>
                <div class="text-xs text-muted-foreground">1 = rare, 10 = common (weighted when it’s easteregg time).</div>
              </div>
              <div class="rounded-md bg-muted px-2 py-1 text-xs text-muted-foreground">{image.priority ?? 5}</div>
            </div>
            <input
              class="mt-3 w-full"
              type="range"
              min="1"
              max="10"
              step="1"
              value={image.priority ?? 5}
              on:change={(e) => onSetPriority(image.filename, Number(e.currentTarget.value))}
            />
            <div class="mt-1 flex justify-between text-[11px] text-muted-foreground">
              <span>Rare</span>
              <span>Common</span>
            </div>
          </div>

          <div class="pt-1">
            <button class={cls(ui.button, ui.buttonDestructive)} on:click={remove} disabled={deleting}>
              {deleting ? "Deleting…" : "Delete easteregg"}
            </button>
            <div class="mt-2 text-xs text-muted-foreground">Deletion can’t be undone.</div>
          </div>
        </div>
      </div>
    </section>
  {/if}
</div>


