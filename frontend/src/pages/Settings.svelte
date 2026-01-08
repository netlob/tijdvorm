<script>
  import { onMount, onDestroy } from "svelte";
  import { cls, ui } from "../lib/ui.js";

  export let settings = { easter_egg_chance_denominator: 10 };
  export let saving = false;
  export let error = "";

  export let onSave = async () => {};
  export let onRefresh = async () => {};

  let logs = [];
  let socket;
  let logContainer;
  let pm2Loading = null;

  async function controlPm2(service, action) {
    if (confirm(`Are you sure you want to ${action} ${service}?`)) {
        pm2Loading = `${service}-${action}`;
        try {
            const res = await fetch(`/api/pm2/${service}/${action}`, { method: "POST" });
            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || "Failed");
            alert(`Success: ${action} ${service}`);
        } catch (e) {
            alert(`Error: ${e.message}`);
        } finally {
            pm2Loading = null;
        }
    }
  }

  function connectWs() {
      // Use relative path so it works through Vite proxy or in prod
      const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
      const host = window.location.host;
      const url = `${protocol}//${host}/api/ws/logs/tv`;
      
      console.log("Connecting to logs WS:", url);
      socket = new WebSocket(url);
      
      socket.onmessage = (event) => {
          logs = [...logs, event.data].slice(-500); // Keep last 500 lines
          if (logContainer) {
             // Auto-scroll if we were near bottom or just always? 
             // Always for now.
             setTimeout(() => {
                 if(logContainer) logContainer.scrollTop = logContainer.scrollHeight;
             }, 0);
          }
      };
      
      socket.onclose = () => {
          console.log("WS closed, retrying in 3s...");
          // Clear socket to prevent multiple listeners if we reconnect
          socket = null;
          setTimeout(connectWs, 3000);
      };
      
      socket.onerror = (err) => {
          console.error("WS error:", err);
          if (socket) socket.close();
      }
  }

  onMount(() => {
    connectWs();
  });

  onDestroy(() => {
    if (socket) {
        socket.onclose = null; // Prevent retry
        socket.close();
    }
  });
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

  <section class={ui.card}>
    <div class={ui.cardHeader}>
      <div class={ui.cardTitle}>Live Logs (TV)</div>
      <div class={ui.cardDesc}>Real-time output from the background process.</div>
    </div>
    <div class={ui.cardContent}>
      <div class="mb-4 flex flex-wrap gap-4">
        {#each ["tv", "backend", "frontend"] as service}
           <div class="flex items-center gap-2 border p-2 rounded bg-muted/20">
             <span class="font-bold uppercase text-xs w-16">{service}</span>
             <div class="flex gap-1">
               <button 
                 class="px-2 py-1 bg-green-600 text-white text-xs rounded hover:bg-green-700 disabled:opacity-50"
                 on:click={() => controlPm2(service, "start")}
                 disabled={!!pm2Loading}
               >Start</button>
               <button 
                 class="px-2 py-1 bg-yellow-600 text-white text-xs rounded hover:bg-yellow-700 disabled:opacity-50"
                 on:click={() => controlPm2(service, "restart")}
                 disabled={!!pm2Loading}
               >Restart</button>
               <button 
                 class="px-2 py-1 bg-red-600 text-white text-xs rounded hover:bg-red-700 disabled:opacity-50"
                 on:click={() => controlPm2(service, "stop")}
                 disabled={!!pm2Loading}
               >Stop</button>
             </div>
           </div>
        {/each}
      </div>

      <div 
        bind:this={logContainer}
        class="bg-black text-white p-4 rounded-md font-mono text-xs h-96 overflow-y-auto whitespace-pre-wrap leading-tight"
      >
        {#each logs as log}
          <div>{log}</div>
        {/each}
      </div>
    </div>
  </section>
</div>


