export const cls = (...parts) => parts.filter(Boolean).join(" ");

export const ui = {
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


