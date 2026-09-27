export function labelColor(label: string): string {
  const words = label.toLowerCase().split(/[^a-zäöüß]+/);
  if (words.some((word) => ["bug", "fehler", "defect"].includes(word)))
    return "github-red";
  if (
    words.some((word) =>
      ["feature", "enhancement", "verbesserung"].includes(word),
    )
  )
    return "github-blue";
  return "github-neutral";
}

export function localStatusColor(status: string): string {
  return (
    (
      {
        new: "github-blue",
        in_progress: "github-amber",
        done: "github-green",
        archived: "github-neutral",
      } as Record<string, string>
    )[status] || "github-neutral"
  );
}
