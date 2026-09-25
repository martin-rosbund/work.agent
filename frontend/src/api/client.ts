export let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export async function api<T = any>(
  path: string,
  method = "GET",
  body?: any,
  extra: Record<string, string> = {},
): Promise<T> {
  const form = body instanceof FormData;
  const response = await fetch("/api/v1" + path, {
    method,
    credentials: "same-origin",
    headers: {
      ...(form ? {} : { "Content-Type": "application/json" }),
      ...(method === "GET" ? {} : { "X-CSRF-Token": csrf }),
      ...extra,
    },
    body: body === undefined ? undefined : form ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    let error: any;
    try {
      error = await response.json();
    } catch {
      error = { detail: "Der Dienst ist gerade nicht erreichbar." };
    }
    if (
      response.status === 401 &&
      !path.startsWith("/auth") &&
      !path.startsWith("/microsoft")
    )
      window.dispatchEvent(new Event("session-expired"));
    throw new Error(
      typeof error.detail === "string"
        ? error.detail
        : "Bitte die Eingaben prüfen.",
    );
  }
  return response.json();
}
