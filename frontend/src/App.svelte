<script>
  import { route, goto } from "./lib/router.js";
  import BottomNav from "./components/BottomNav.svelte";
  import Home from "./pages/Home.svelte";
  import EggDetail from "./pages/EggDetail.svelte";
  import Settings from "./pages/Settings.svelte";
  import {
    apiDeleteImage,
    apiGetLivePreview,
    apiGetOverride,
    apiGetSettings,
    apiListImages,
    apiSaveSettings,
    apiSetEnabled,
    apiSetExplicit,
    apiSetPriority,
    apiSetOverride,
    apiUpload
  } from "./lib/api.js";

  let images = [];
  let override = { filename: null, set_at: null };
  let settings = { easter_egg_chance_denominator: 10 };
  let livePreview = { updated_at: null, type: null, filename: null, url: null };

  let loading = true;
  let error = "";
  let savingSettings = false;
  let busy = false;

  $: current = $route;
  $: activeTab = current?.name === "settings" ? "settings" : "home";
  $: selected =
    current?.name === "egg" ? images.find((img) => img.filename === current.filename) ?? null : null;

  async function refresh() {
    loading = true;
    error = "";
    try {
      const [imgs, ovr, sett, live] = await Promise.all([
        apiListImages(),
        apiGetOverride(),
        apiGetSettings(),
        apiGetLivePreview()
      ]);
      images = imgs;
      override = ovr;
      settings = sett;
      livePreview = live;
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      loading = false;
    }
  }

  async function upload(file) {
    error = "";
    try {
      await apiUpload(file);
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
      throw e;
    }
  }

  async function setEnabled(filename, enabled) {
    error = "";
    try {
      await apiSetEnabled(filename, enabled);
      images = images.map((img) => (img.filename === filename ? { ...img, enabled } : img));
    } catch (e) {
      error = e?.message ?? String(e);
      await refresh();
    }
  }

  async function setExplicit(filename, explicit) {
    error = "";
    try {
      await apiSetExplicit(filename, explicit);
      images = images.map((img) => (img.filename === filename ? { ...img, explicit } : img));
    } catch (e) {
      error = e?.message ?? String(e);
      await refresh();
    }
  }

  async function setPriority(filename, priority) {
    error = "";
    try {
      await apiSetPriority(filename, priority);
      images = images.map((img) => (img.filename === filename ? { ...img, priority } : img));
    } catch (e) {
      error = e?.message ?? String(e);
      await refresh();
    }
  }

  async function setOverride(filenameOrNull) {
    busy = true;
    error = "";
    try {
      await apiSetOverride(filenameOrNull);
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      busy = false;
    }
  }

  async function removeImage(filename) {
    error = "";
    try {
      await apiDeleteImage(filename);
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
      throw e;
    }
  }

  async function saveSettings() {
    savingSettings = true;
    error = "";
    try {
      await apiSaveSettings(settings);
      await refresh();
    } catch (e) {
      error = e?.message ?? String(e);
    } finally {
      savingSettings = false;
    }
  }

  refresh();
</script>

<div class="min-h-[100dvh]">
  <header
    class="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75"
    style="padding-top: env(safe-area-inset-top);"
  >
    <div class="mx-auto flex w-full max-w-[960px] items-center justify-between gap-3 px-4 py-3 sm:px-6">
      <div class="min-w-0">
        <div class="truncate text-base font-semibold tracking-tight">tijdvorm</div>
        <div class="truncate text-xs text-muted-foreground">
          {#if current?.name === "settings"}Settings{:else if current?.name === "egg"}Easteregg details{:else}Eastereggs{/if}
        </div>
      </div>
      {#if current?.name === "egg"}
        <button class="text-xs text-muted-foreground hover:text-foreground" on:click={() => goto("/")}>Home</button>
      {/if}
    </div>
  </header>

  <main
    class="mx-auto w-full max-w-[960px] px-4 pt-4 sm:px-6"
    style="padding-bottom: calc(var(--tabbar-h) + env(safe-area-inset-bottom) + 16px);"
  >
    {#if current?.name === "settings"}
      <Settings {settings} saving={savingSettings} {error} onSave={saveSettings} onRefresh={refresh} />
    {:else if current?.name === "egg"}
      <EggDetail
        image={selected}
        {override}
        busy={busy || loading}
        {error}
        onBack={() => history.length > 1 ? history.back() : goto("/")}
        onRefresh={refresh}
        onSetOverride={setOverride}
        onSetEnabled={setEnabled}
        onSetExplicit={setExplicit}
        onSetPriority={setPriority}
        onDelete={removeImage}
        onDeleted={() => goto("/")}
      />
    {:else}
      <Home
        {images}
        {override}
        {loading}
        {error}
        {livePreview}
        onRefresh={refresh}
        onOpenEgg={(f) => goto(`/egg/${encodeURIComponent(f)}`)}
        onUpload={upload}
      />
    {/if}
  </main>

  <BottomNav active={activeTab} />
</div>
