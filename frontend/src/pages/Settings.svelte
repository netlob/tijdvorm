<script>
  import { cls, ui } from "../lib/ui.js";

  export let settings = { easter_egg_chance_denominator: 10 };
  export let saving = false;
  export let error = "";

  export let onSave = async () => {};
  export let onRefresh = async () => {};
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

  <section class={ui.card}>
    <div class={ui.cardHeader}>
      <div class="flex items-start justify-between gap-3">
        <div>
          <div class={ui.cardTitle}>Frequency</div>
          <div class={ui.cardDesc}>How often an easter egg shows up.</div>
        </div>
        <button class={cls(ui.button, ui.buttonSecondary)} on:click={onRefresh}>Refresh</button>
      </div>
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
              (settings.easter_egg_chance_denominator = Number(e.currentTarget.value) )}
          />
        </label>
        <button class={cls(ui.button, ui.buttonPrimary)} on:click={onSave} disabled={saving}>
          {saving ? "Saving…" : "Save"}
        </button>
        <p class="text-xs text-muted-foreground">0 = never. 1 = every minute. 10 = ~10% chance.</p>
      </div>
    </div>
  </section>

  <section class={ui.card}>
    <div class={ui.cardHeader}>
      <div class={ui.cardTitle}>App</div>
      <div class={ui.cardDesc}>A nicer “home screen app” layout for iOS.</div>
    </div>
    <div class={ui.cardContent}>
      <div class="text-sm text-muted-foreground">
        Tip: if you already added it to your home screen, restarting Safari after updates helps it pick up new UI.
      </div>
    </div>
  </section>
</div>


