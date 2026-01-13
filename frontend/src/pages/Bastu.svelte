<script>
  import { onMount } from "svelte";
  import { cls, ui } from "../lib/ui.js";

  export let livePreview;
  export let onRefresh = async () => {};

  let previewUrl = null;
  
  // Force update when livePreview changes
  $: if (livePreview?.url) {
      previewUrl = livePreview.url + "?t=" + new Date().getTime();
  }

  // Poll for updates if it's currently showing
  let interval;
  onMount(() => {
     interval = setInterval(onRefresh, 5000);
     return () => clearInterval(interval);
  });
</script>

<div class="flex flex-col items-center justify-center min-h-[50vh] gap-6 text-center">
  {#if previewUrl}
    <div class="relative w-full max-w-sm aspect-[9/16] bg-black rounded-lg overflow-hidden shadow-2xl border border-border">
      <img
        src={previewUrl}
        alt="Sauna Live Preview"
        class="w-full h-full object-cover"
      />
      <div class="absolute bottom-0 left-0 right-0 bg-black/60 text-white text-xs p-2 backdrop-blur-sm">
         Last updated: {livePreview.updated_at ? new Date(livePreview.updated_at).toLocaleTimeString() : 'Unknown'}
      </div>
    </div>
  {:else}
     <div class="text-muted-foreground p-8 border rounded-lg bg-muted/10">
        No live preview available.
     </div>
  {/if}
</div>

