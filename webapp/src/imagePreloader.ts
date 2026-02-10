export type ImageSourceKind = "local_asset" | "backend" | "external";

export type ImagePreloadResult = {
  requestedUrl: string;
  normalizedUrl: string;
  source: ImageSourceKind;
  ok: boolean;
  fromCache: boolean;
  durationMs: number;
};

function normalizeImageUrl(url: string): string {
  return (url || "").trim();
}

function detectImageSource(url: string): ImageSourceKind {
  if (!url) return "local_asset";
  if (/^https?:\/\//i.test(url)) {
    try {
      const parsed = new URL(url);
      const origin = typeof window !== "undefined" ? window.location.origin : "";
      return origin && parsed.origin === origin ? "backend" : "external";
    } catch {
      return "external";
    }
  }
  if (url.startsWith("/api/") || url.includes("/api/")) {
    return "backend";
  }
  return "local_asset";
}

class ImagePreloader {
  private loaded = new Set<string>();
  private inflight = new Map<string, Promise<ImagePreloadResult>>();
  private durationsMs = new Map<string, number>();

  isLoaded(url: string): boolean {
    const normalized = normalizeImageUrl(url);
    return normalized ? this.loaded.has(normalized) : false;
  }

  getDuration(url: string): number | null {
    const normalized = normalizeImageUrl(url);
    if (!normalized) return null;
    return this.durationsMs.has(normalized) ? this.durationsMs.get(normalized) ?? null : null;
  }

  preload(url: string): Promise<ImagePreloadResult> {
    const normalized = normalizeImageUrl(url);
    if (!normalized) {
      return Promise.resolve({
        requestedUrl: url,
        normalizedUrl: normalized,
        source: "local_asset",
        ok: false,
        fromCache: true,
        durationMs: 0,
      });
    }

    if (this.loaded.has(normalized)) {
      return Promise.resolve({
        requestedUrl: url,
        normalizedUrl: normalized,
        source: detectImageSource(normalized),
        ok: true,
        fromCache: true,
        durationMs: 0,
      });
    }

    const inflightRequest = this.inflight.get(normalized);
    if (inflightRequest) {
      return inflightRequest;
    }

    const startedAt = performance.now();
    const task = new Promise<ImagePreloadResult>((resolve) => {
      const image = new Image();
      image.onload = () => {
        const durationMs = performance.now() - startedAt;
        this.loaded.add(normalized);
        this.durationsMs.set(normalized, durationMs);
        resolve({
          requestedUrl: url,
          normalizedUrl: normalized,
          source: detectImageSource(normalized),
          ok: true,
          fromCache: false,
          durationMs,
        });
      };
      image.onerror = () => {
        const durationMs = performance.now() - startedAt;
        resolve({
          requestedUrl: url,
          normalizedUrl: normalized,
          source: detectImageSource(normalized),
          ok: false,
          fromCache: false,
          durationMs,
        });
      };
      image.src = normalized;
    }).finally(() => {
      this.inflight.delete(normalized);
    });

    this.inflight.set(normalized, task);
    return task;
  }
}

export const imagePreloader = new ImagePreloader();
