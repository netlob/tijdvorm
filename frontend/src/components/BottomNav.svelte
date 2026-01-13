<script>
  import { cls } from "../lib/ui.js";
  import { goto } from "../lib/router.js";

  export let active = "home";

  const itemBase =
    "flex flex-1 flex-col items-center justify-center gap-1 rounded-xl px-2 py-2 text-xs transition-colors";
  const activeCls = "text-foreground";
  const inactiveCls = "text-muted-foreground hover:text-foreground";
</script>

<nav
  class="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/75"
  style="padding-bottom: env(safe-area-inset-bottom); height: calc(var(--tabbar-h) + env(safe-area-inset-bottom));"
  aria-label="Bottom navigation"
>
  <div class="mx-auto flex h-[var(--tabbar-h)] w-full max-w-[960px] items-stretch px-3">
    <button
      type="button"
      class={cls(itemBase, active === "home" ? activeCls : inactiveCls)}
      on:click={() => goto("/")}
      aria-current={active === "home" ? "page" : undefined}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" class="opacity-90">
        <path
          d="M4 10.5L12 4l8 6.5V20a1 1 0 0 1-1 1h-5v-6H10v6H5a1 1 0 0 1-1-1v-9.5Z"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linejoin="round"
        />
      </svg>
      <span>Eastereggs</span>
    </button>

    <button
      type="button"
      class={cls(itemBase, active === "bastu" ? activeCls : inactiveCls)}
      on:click={() => goto("/bastu")}
      aria-current={active === "bastu" ? "page" : undefined}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" class="opacity-90">
         <path stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M12 21v-8m0 8-3-3m3 3 3-3"/>
         <path stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M8 5a4 4 0 0 1 8 0v8a4 4 0 0 1-8 0V5z"/>
         <path stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" d="M6 10a6 6 0 0 0 12 0"/>
      </svg>
      <span>Bastu</span>
    </button>

    <button
      type="button"
      class={cls(itemBase, active === "settings" ? activeCls : inactiveCls)}
      on:click={() => goto("/settings")}
      aria-current={active === "settings" ? "page" : undefined}
    >
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" class="opacity-90">
        <path
          d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"
          stroke="currentColor"
          stroke-width="1.8"
        />
        <path
          d="M19.4 15a8.3 8.3 0 0 0 .1-1l2-1.2-2-3.4-2.3.4a7.3 7.3 0 0 0-1.7-1l-.3-2.4H9.9l-.3 2.4a7.3 7.3 0 0 0-1.7 1l-2.3-.4-2 3.4 2 1.2a8.3 8.3 0 0 0 0 2l-2 1.2 2 3.4 2.3-.4a7.3 7.3 0 0 0 1.7 1l.3 2.4h4.2l.3-2.4a7.3 7.3 0 0 0 1.7-1l2.3.4 2-3.4-2-1.2Z"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linejoin="round"
        />
      </svg>
      <span>Settings</span>
    </button>
  </div>
</nav>


