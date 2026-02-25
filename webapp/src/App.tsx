import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type ApiConfig } from "./api";
import { imagePreloader, type ImagePreloadResult } from "./imagePreloader";
import type { GameFormat, GameMode, RoomInfo, RoomPlayer, TurnState } from "./types";

const tg = (window as any).Telegram?.WebApp;

type Screen =
  | "loading"
  | "format"
  | "playMode"
  | "randomInfo"
  | "onlineMenu"
  | "roomCreateSettings"
  | "roomCreateRandomSettings"
  | "offlinePlayers"
  | "offlinePlayer"
  | "offlineRole"
  | "offlineNext"
  | "offlineFinished"
  | "offlineTurn"
  | "joinRoom"
  | "room"
  | "roomGame";

type OfflineTurnStatus = {
  timer_enabled: boolean;
  turn_time_seconds?: number | null;
  turn_active: boolean;
  turn_state: TurnState;
  current_turn_index: number;
  current_player_number: number;
  turn_started_at?: number | null;
  turns_completed: boolean;
};

type RolePayload = {
  role: string;
  card?: string;
  image_url?: string;
  elixir_cost?: number | null;
};

const MIN_PLAYERS = 3;
const MAX_PLAYERS = 12;
const GENERIC_ERROR_MESSAGE = "Произошла ошибка, попробуйте ещё раз";
const RANDOM_SCENARIOS = [
  { id: "standard", label: "Стандартный (обычный режим)" },
  { id: "all_spies", label: "Все шпионы" },
  { id: "same_card", label: "У всех одна карта" },
  { id: "one_outlier_card", label: "У одного игрока другая карта" },
  { id: "different_cards", label: "У всех разные карты" },
  { id: "multi_spy", label: "Несколько шпионов" },
];

const DEFAULT_RANDOM_ALLOWED = RANDOM_SCENARIOS.map((scenario) => scenario.id);
const ROOM_DEV_LOGS = import.meta.env.DEV || import.meta.env.VITE_ROOM_DEBUG === "1";
const IMAGE_DEBUG_LOGS =
  ROOM_DEV_LOGS || import.meta.env.VITE_CARD_IMAGE_DEBUG === "1" || import.meta.env.VITE_IMAGE_DEBUG === "1";
const TOAST_DURATION_MS = 4800;
const HOME_BG_URL = "/assets/newBack.png";
const HOME_HERO_BANNER_URL = "/assets/blindBan.png";
const GAME_BG_URL = "/assets/cardBan-v2.jpg";
const SPY_IMAGE_URL = "/assets/spy1-v2.png";
const ELIXIR_IMAGE_URL = "/assets/elik-v2.png";
const ROLE_MODAL_ANIM_MS = 220;
const FREQUENT_CARD_IMAGE_URLS = [
  "Рыцарь",
  "Лучницы",
  "Всадник на кабане",
  "Ведьма",
  "П.Е.К.К.А.",
  "Рыбак",
].map((name) => `/api/cards/image?name=${encodeURIComponent(name)}`);
const CRITICAL_ASSET_URLS = [HOME_BG_URL, HOME_HERO_BANNER_URL, GAME_BG_URL, SPY_IMAGE_URL, ELIXIR_IMAGE_URL];

const IconOffline = () => (
  <svg viewBox="0 0 24 24" fill="none">
    <rect x="7" y="2.5" width="10" height="19" rx="2.5" />
    <circle cx="12" cy="18.5" r="1.1" fill="currentColor" stroke="none" />
    <path d="M10.3 5.7h3.4" />
  </svg>
);

const IconOnline = () => (
  <svg viewBox="0 0 24 24" fill="none">
    <path d="M12 19.5a7.5 7.5 0 1 0 0-15 7.5 7.5 0 0 0 0 15Z" />
    <path d="M4.5 12h15" />
    <path d="M12 4.5c2.2 2.1 2.2 12.9 0 15" />
    <path d="M12 4.5c-2.2 2.1-2.2 12.9 0 15" />
  </svg>
);

const IconCreateRoom = () => (
  <svg viewBox="0 0 24 24" fill="none">
    <path d="M4 11V7.5A2.5 2.5 0 0 1 6.5 5h11A2.5 2.5 0 0 1 20 7.5V11" />
    <path d="M4 11h16v7.5a2.5 2.5 0 0 1-2.5 2.5h-11A2.5 2.5 0 0 1 4 18.5V11Z" />
    <path d="M12 8.2v5.6" />
    <path d="M9.2 11h5.6" />
  </svg>
);

const IconJoinRoom = () => (
  <svg viewBox="0 0 24 24" fill="none">
    <rect x="3" y="4" width="14" height="16" rx="2.2" />
    <path d="m14.5 12 6.5 0" />
    <path d="m18.5 9 3 3-3 3" />
    <path d="M7.7 9.5h4.4" />
    <path d="M7.7 13h4.4" />
  </svg>
);

const IconShowCard = () => (
  <svg viewBox="0 0 24 24" fill="none">
    <rect x="4" y="5" width="13" height="16" rx="2.4" />
    <path d="M8 9.2h5.1" />
    <path d="M8 12.4h5.1" />
    <path d="M8 15.6h3.2" />
    <path d="M17 8.2 20.6 10l-3.6 1.8" />
  </svg>
);

const IconStart = () => (
  <svg viewBox="0 0 24 24" fill="none">
    <circle cx="12" cy="12" r="8.5" />
    <path d="m10 8.8 5.1 3.2-5.1 3.2V8.8Z" fill="currentColor" stroke="none" />
  </svg>
);

function toUserError(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback;
}

function normalizeRoomCode(code: string): string {
  return (code ?? "")
    .normalize("NFKC")
    .replace(/\s+/g, "")
    .replace(/[^0-9a-zA-Z]/g, "")
    .toUpperCase();
}

function isRoomGoneError(message: string): boolean {
  const normalized = (message || "").toLowerCase();
  return (
    normalized.includes("room not found") ||
    normalized.includes("комната не найдена") ||
    normalized.includes("вы вышли из комнаты") ||
    normalized.includes("not in room")
  );
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [format, setFormat] = useState<GameFormat | null>(null);
  const [gameMode, setGameMode] = useState<GameMode | null>(null);
  const [randomAllowed, setRandomAllowed] = useState<string[]>(DEFAULT_RANDOM_ALLOWED);
  const [roomPlayerLimit, setRoomPlayerLimit] = useState<number | null>(null);

  const [timerEnabled, setTimerEnabled] = useState<boolean>(false);
  const [turnTimeSeconds, setTurnTimeSeconds] = useState<number>(8);

  const [pendingOfflineCount, setPendingOfflineCount] = useState<number | null>(null);
  const [offlineSessionId, setOfflineSessionId] = useState<string | null>(null);
  const [offlineTimerEnabled, setOfflineTimerEnabled] = useState<boolean>(false);
  const [currentPlayer, setCurrentPlayer] = useState<number>(1);
  const [offlineRole, setOfflineRole] = useState<{
    role: string;
    card?: string;
    image_url?: string;
    elixir_cost?: number | null;
  } | null>(null);
  const [offlineImageOk, setOfflineImageOk] = useState<boolean>(true);
  const [offlineCardImageLoaded, setOfflineCardImageLoaded] = useState<boolean>(false);
  const [starterPlayer, setStarterPlayer] = useState<number | null>(null);
  const [offlineTurn, setOfflineTurn] = useState<OfflineTurnStatus | null>(null);

  const [roomInfo, setRoomInfo] = useState<RoomInfo | null>(null);
  const [roomCodeInput, setRoomCodeInput] = useState<string>("");
  const [roomRole, setRoomRole] = useState<RolePayload | null>(null);
  const [isRoomRoleOpen, setIsRoomRoleOpen] = useState<boolean>(false);
  const [isRoomRoleMounted, setIsRoomRoleMounted] = useState<boolean>(false);
  const [isRoomRoleAnimatingOut, setIsRoomRoleAnimatingOut] = useState<boolean>(false);
  const [roomImageOk, setRoomImageOk] = useState<boolean>(true);
  const [roomCardImageLoaded, setRoomCardImageLoaded] = useState<boolean>(false);
  const [roomStarter, setRoomStarter] = useState<string | null>(null);
  const [showRoomDevTools, setShowRoomDevTools] = useState<boolean>(false);
  const [roomCodeTapCount, setRoomCodeTapCount] = useState<number>(0);
  const [devActionLoading, setDevActionLoading] = useState<boolean>(false);
  const [homeBannerLoadFailed, setHomeBannerLoadFailed] = useState<boolean>(false);
  const leaveSentRef = useRef<boolean>(false);
  const toastSeqRef = useRef<number>(0);
  const prevRoomInfoRef = useRef<RoomInfo | null>(null);
  const lastForcedRoomStartToastKeyRef = useRef<string>("");
  const offlineRoleImageRenderStartedAtRef = useRef<number | null>(null);
  const roomRoleImageRenderStartedAtRef = useRef<number | null>(null);
  const roomRoleCloseTimerRef = useRef<number | null>(null);
  const roomRoleOpenRafRef = useRef<number | null>(null);

  const [turnRemainingMs, setTurnRemainingMs] = useState<number | null>(null);
  const [toasts, setToasts] = useState<Array<{ id: number; text: string }>>([]);
  const [assetsReady, setAssetsReady] = useState<boolean>(false);
  const [displayedBackgroundUrl, setDisplayedBackgroundUrl] = useState<string>(HOME_BG_URL);
  const [backgroundReady, setBackgroundReady] = useState<boolean>(false);

  const [initData, setInitData] = useState<string>(() => tg?.initData ?? "");
  const apiBase = import.meta.env.VITE_API_BASE ?? "";
  const screenRef = useRef<Screen>(screen);

  const resolveImageUrl = (url: string) => {
    if (/^https?:\/\//i.test(url)) return url;
    if (!apiBase) return url;
    const trimmed = apiBase.replace(/\/$/, "");
    return `${trimmed}${url.startsWith("/") ? "" : "/"}${url}`;
  };

  const logImageDebug = useCallback((event: string, payload: Record<string, unknown>) => {
    if (!IMAGE_DEBUG_LOGS) return;
    console.info(`[image_debug] ${event}`, payload);
  }, []);

  const preloadRoleCardImage = useCallback(
    async (rawUrl?: string, source?: string): Promise<ImagePreloadResult | null> => {
      if (!rawUrl) return null;
      const resolvedSrc = resolveImageUrl(rawUrl);
      const result = await imagePreloader.preload(resolvedSrc);
      logImageDebug("card_preload", {
        source: source ?? "unknown",
        src: result.normalizedUrl,
        source_kind: result.source,
        ok: result.ok,
        from_cache: result.fromCache,
        duration_ms: Number(result.durationMs.toFixed(1)),
      });
      return result;
    },
    [apiBase, logImageDebug]
  );

  const handleOfflineCardImageLoad = useCallback((src: string) => {
    setOfflineCardImageLoaded(true);
    const startedAt = offlineRoleImageRenderStartedAtRef.current;
    const renderDuration = startedAt ? performance.now() - startedAt : null;
    logImageDebug("card_render_loaded_offline", {
      src,
      render_duration_ms: renderDuration !== null ? Number(renderDuration.toFixed(1)) : null,
      preload_duration_ms:
        imagePreloader.getDuration(src) !== null ? Number((imagePreloader.getDuration(src) ?? 0).toFixed(1)) : null,
    });
  }, [logImageDebug]);

  const handleRoomCardImageLoad = useCallback((src: string) => {
    setRoomCardImageLoaded(true);
    const startedAt = roomRoleImageRenderStartedAtRef.current;
    const renderDuration = startedAt ? performance.now() - startedAt : null;
    logImageDebug("card_render_loaded_room", {
      src,
      render_duration_ms: renderDuration !== null ? Number(renderDuration.toFixed(1)) : null,
      preload_duration_ms:
        imagePreloader.getDuration(src) !== null ? Number((imagePreloader.getDuration(src) ?? 0).toFixed(1)) : null,
    });
  }, [logImageDebug]);

  const fetchCardMeta = useCallback(
    async (cardName: string) => {
      const normalized = cardName.trim();
      if (!normalized) {
        throw new Error("Не указано название карты");
      }

      const base = apiBase.replace(/\/$/, "");
      const endpoint = `${base}/api/cards/meta?name=${encodeURIComponent(normalized)}`;
      const res = await fetch(endpoint);
      if (!res.ok) {
        let message = "Не удалось получить данные карты";
        const text = await res.text();
        if (text && res.status < 500) {
          try {
            const data = JSON.parse(text);
            if (data?.detail) {
              message = data.detail;
            } else {
              message = text;
            }
          } catch {
            message = text;
          }
        }
        throw new Error(message);
      }

      return (await res.json()) as {
        name: string;
        image_url?: string | null;
        elixir_cost?: number | null;
      };
    },
    [apiBase]
  );

  const apiConfig: ApiConfig = useMemo(() => ({ baseUrl: apiBase, initData }), [apiBase, initData]);
  const canUseRoomPreviewTools = Boolean(
    roomInfo &&
      screen === "room" &&
      roomInfo.you_are_owner
  );
  const canUseRoomDevTools = Boolean(
    roomInfo &&
      screen === "room" &&
      roomInfo.you_are_owner &&
      roomInfo.can_manage_bots
  );
  const pushToast = useCallback((text: string) => {
    const message = (text || "").trim();
    if (!message) return;
    const id = ++toastSeqRef.current;
    setToasts((prev) => [...prev, { id, text: message }]);
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((item) => item.id !== id));
    }, TOAST_DURATION_MS);
  }, []);

  const clearRoomRoleCloseTimer = useCallback(() => {
    if (roomRoleCloseTimerRef.current !== null) {
      window.clearTimeout(roomRoleCloseTimerRef.current);
      roomRoleCloseTimerRef.current = null;
    }
  }, []);

  const clearRoomRoleOpenRaf = useCallback(() => {
    if (roomRoleOpenRafRef.current !== null) {
      window.cancelAnimationFrame(roomRoleOpenRafRef.current);
      roomRoleOpenRafRef.current = null;
    }
  }, []);

  const forceCloseRoomRoleModal = useCallback(() => {
    clearRoomRoleOpenRaf();
    clearRoomRoleCloseTimer();
    setIsRoomRoleOpen(false);
    setIsRoomRoleAnimatingOut(false);
    setIsRoomRoleMounted(false);
    setRoomRole(null);
  }, [clearRoomRoleCloseTimer, clearRoomRoleOpenRaf]);

  const closeRoomRoleModal = useCallback(() => {
    if (!isRoomRoleMounted || isRoomRoleAnimatingOut) return;
    clearRoomRoleCloseTimer();
    setIsRoomRoleOpen(false);
    setIsRoomRoleAnimatingOut(true);
    roomRoleCloseTimerRef.current = window.setTimeout(() => {
      setIsRoomRoleAnimatingOut(false);
      setIsRoomRoleMounted(false);
      setRoomRole(null);
      roomRoleCloseTimerRef.current = null;
    }, ROLE_MODAL_ANIM_MS);
  }, [clearRoomRoleCloseTimer, isRoomRoleAnimatingOut, isRoomRoleMounted]);

  const openRoomRoleModal = useCallback(
    (payload: RolePayload) => {
      clearRoomRoleOpenRaf();
      clearRoomRoleCloseTimer();
      setRoomRole(payload);
      setIsRoomRoleAnimatingOut(false);
      setIsRoomRoleMounted(true);
      roomRoleOpenRafRef.current = window.requestAnimationFrame(() => {
        setIsRoomRoleOpen(true);
        roomRoleOpenRafRef.current = null;
      });
    },
    [clearRoomRoleCloseTimer, clearRoomRoleOpenRaf]
  );

  const applyOnlineRoomNavigation = useCallback(
    (info: RoomInfo) => {
      const currentScreen = screenRef.current;
      const prevInfo = prevRoomInfoRef.current;
      const wasStartedOrPaused = Boolean(prevInfo && (prevInfo.state === "started" || prevInfo.state === "paused"));
      const isStartedOrPaused = info.state === "started" || info.state === "paused";
      const enteredStartedOrPaused = isStartedOrPaused && !wasStartedOrPaused;
      const shouldForcePlayingScreen = enteredStartedOrPaused && (currentScreen === "room" || currentScreen === "roomGame");

      if (shouldForcePlayingScreen) {
        forceCloseRoomRoleModal();
        const toastKey = `${info.room_code}:${info.state}:${info.turn_started_at ?? 0}`;
        if (lastForcedRoomStartToastKeyRef.current !== toastKey) {
          lastForcedRoomStartToastKeyRef.current = toastKey;
          pushToast("Игра началась!");
        }
        if (currentScreen !== "roomGame") {
          setScreen("roomGame");
        }
        return;
      }

      if (currentScreen === "roomGame" && info.state === "waiting") {
        forceCloseRoomRoleModal();
        setScreen("room");
      }
    },
    [forceCloseRoomRoleModal, pushToast]
  );

  const renderPlayerName = (player: RoomPlayer) => {
    const baseName = player.display_name?.trim() ? player.display_name : "Не удалось получить имя из Telegram";
    return player.isBot ? `🤖 ${baseName}` : baseName;
  };

  useEffect(() => {
    screenRef.current = screen;
    if (screen !== "roomGame" && screen !== "room" && (isRoomRoleOpen || isRoomRoleMounted)) {
      forceCloseRoomRoleModal();
    }
  }, [forceCloseRoomRoleModal, isRoomRoleMounted, isRoomRoleOpen, screen]);

  useEffect(
    () => () => {
      clearRoomRoleOpenRaf();
      clearRoomRoleCloseTimer();
    },
    [clearRoomRoleCloseTimer, clearRoomRoleOpenRaf]
  );

  useEffect(() => {
    if (screen === "format") {
      setHomeBannerLoadFailed(false);
    }
  }, [screen]);

  useEffect(() => {
    let canceled = false;
    const warmCritical = async () => {
      const results = await Promise.all(CRITICAL_ASSET_URLS.map((url) => imagePreloader.preload(url)));
      for (const result of results) {
        logImageDebug("critical_preload", {
          src: result.normalizedUrl,
          source_kind: result.source,
          ok: result.ok,
          from_cache: result.fromCache,
          duration_ms: Number(result.durationMs.toFixed(1)),
        });
      }
      if (!canceled) setAssetsReady(true);
    };

    void warmCritical();
    void Promise.allSettled(
      FREQUENT_CARD_IMAGE_URLS.map((url) => imagePreloader.preload(resolveImageUrl(url)))
    );

    return () => {
      canceled = true;
    };
  }, [apiBase, logImageDebug]);

  const targetBackgroundUrl = screen === "format" ? HOME_BG_URL : GAME_BG_URL;

  useEffect(() => {
    let canceled = false;
    const applyBackground = async () => {
      if (displayedBackgroundUrl === targetBackgroundUrl && imagePreloader.isLoaded(targetBackgroundUrl)) {
        setBackgroundReady(true);
      }
      const result = await imagePreloader.preload(targetBackgroundUrl);
      logImageDebug("background_preload", {
        src: result.normalizedUrl,
        source_kind: result.source,
        ok: result.ok,
        from_cache: result.fromCache,
        duration_ms: Number(result.durationMs.toFixed(1)),
      });
      if (canceled) return;
      setDisplayedBackgroundUrl(targetBackgroundUrl);
      setBackgroundReady(result.ok || imagePreloader.isLoaded(targetBackgroundUrl));
    };

    void applyBackground();

    return () => {
      canceled = true;
    };
  }, [displayedBackgroundUrl, targetBackgroundUrl, logImageDebug]);

  useEffect(() => {
    tg?.ready?.();
    tg?.expand?.();

    if (initData) return;

    let attempts = 0;
    const interval = setInterval(() => {
      const freshInitData = tg?.initData ?? "";
      if (freshInitData) {
        setError(null);
        setInitData(freshInitData);
        clearInterval(interval);
        return;
      }
      attempts += 1;
      if (attempts >= 5) {
        clearInterval(interval);
        setError("Не удалось получить имя из Telegram. Открой мини‑приложение из Telegram.");
        setScreen("format");
      }
    }, 200);

    return () => clearInterval(interval);
  }, [initData]);

  useEffect(() => {
    if (!initData) return;
    api
      .auth(apiConfig)
      .then(() => setScreen("format"))
      .catch((err) => {
        setError(toUserError(err, "Не удалось подтвердить Telegram"));
        setScreen("format");
      });
  }, [apiConfig, initData]);

  useEffect(() => {
    if (screen === "randomInfo") {
      setRandomAllowed(DEFAULT_RANDOM_ALLOWED);
    }
  }, [screen]);

  useEffect(() => {
    if (!timerEnabled) {
      setTurnTimeSeconds(8);
    }
  }, [timerEnabled]);

  useEffect(() => {
    if (!roomInfo || (screen !== "room" && screen !== "roomGame")) return;

    let canceled = false;
    const poll = async () => {
      try {
        const info = await api.roomStatus(apiConfig, roomInfo.room_code);
        if (canceled) return;
        setRoomInfo(info);
        if (info.state === "started" || info.state === "paused") {
          const starter = info.starter_name ? `Игру начинает: ${info.starter_name}` : "Игра началась";
          setRoomStarter((prev) => prev ?? starter);
        }
        applyOnlineRoomNavigation(info);
      } catch (err) {
        if (canceled) return;
        const message = toUserError(err, "");
        if (isRoomGoneError(message)) {
          resetAll();
          setError("Комната закрыта или вы вышли из неё");
        }
      }
    };

    poll();
    const interval = setInterval(poll, 1000);
    return () => {
      canceled = true;
      clearInterval(interval);
    };
  }, [apiConfig, applyOnlineRoomNavigation, roomInfo?.room_code, screen]);

  useEffect(() => {
    if (!roomInfo || (screen !== "room" && screen !== "roomGame")) return;

    let canceled = false;
    const ping = async () => {
      try {
        const info = await api.roomHeartbeat(apiConfig, roomInfo.room_code);
        if (canceled) return;
        setRoomInfo(info);
        applyOnlineRoomNavigation(info);
      } catch (err) {
        if (canceled) return;
        const message = toUserError(err, "");
        if (isRoomGoneError(message)) {
          resetAll();
          setError("Комната закрыта или вы вышли из неё");
        }
      }
    };

    ping();
    const interval = setInterval(ping, 8000);
    return () => {
      canceled = true;
      clearInterval(interval);
    };
  }, [apiConfig, applyOnlineRoomNavigation, roomInfo?.room_code, screen]);

  useEffect(() => {
    if (!roomInfo || (screen !== "room" && screen !== "roomGame")) return;

    leaveSentRef.current = false;
    const endpoint = apiBase ? `${apiBase.replace(/\/$/, "")}/api/room/leave` : "/api/room/leave";
    const payload = JSON.stringify({ initData, room_code: roomInfo.room_code });
    const sendLeaveSignal = () => {
      if (leaveSentRef.current) return;
      leaveSentRef.current = true;

      let delivered = false;
      try {
        if (navigator.sendBeacon) {
          const blob = new Blob([payload], { type: "application/json" });
          delivered = navigator.sendBeacon(endpoint, blob);
        }
      } catch {
        delivered = false;
      }

      if (!delivered) {
        fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: payload,
          keepalive: true,
        }).catch(() => undefined);
      }
    };

    let hiddenTimer: number | null = null;
    const onVisibilityChange = () => {
      if (document.visibilityState === "hidden") {
        if (hiddenTimer !== null) {
          window.clearTimeout(hiddenTimer);
        }
        hiddenTimer = window.setTimeout(() => {
          if (document.visibilityState === "hidden") {
            sendLeaveSignal();
          }
        }, 15000);
        return;
      }
      if (hiddenTimer !== null) {
        window.clearTimeout(hiddenTimer);
        hiddenTimer = null;
      }
    };
    const onPageHide = () => sendLeaveSignal();
    const onBeforeUnload = () => sendLeaveSignal();

    document.addEventListener("visibilitychange", onVisibilityChange);
    window.addEventListener("pagehide", onPageHide);
    window.addEventListener("beforeunload", onBeforeUnload);

    return () => {
      document.removeEventListener("visibilitychange", onVisibilityChange);
      window.removeEventListener("pagehide", onPageHide);
      window.removeEventListener("beforeunload", onBeforeUnload);
      if (hiddenTimer !== null) {
        window.clearTimeout(hiddenTimer);
      }
      leaveSentRef.current = false;
    };
  }, [apiBase, initData, roomInfo?.room_code, screen]);

  useEffect(() => {
    if (screen !== "offlineTurn" || !offlineSessionId || !offlineTimerEnabled || offlineTurn?.turn_state === "finished") {
      return;
    }

    let canceled = false;
    const poll = async () => {
      try {
        const info = await api.offlineTurnStatus(apiConfig, offlineSessionId);
        if (!canceled) {
          setOfflineTurn(info);
        }
      } catch (err) {
        if (!canceled) {
          setError(toUserError(err, GENERIC_ERROR_MESSAGE));
        }
      }
    };

    poll();
    const interval = setInterval(poll, 700);
    return () => {
      canceled = true;
      clearInterval(interval);
    };
  }, [apiConfig, offlineSessionId, offlineTimerEnabled, offlineTurn?.turn_state, screen]);

  useEffect(() => {
    setOfflineImageOk(true);
    offlineRoleImageRenderStartedAtRef.current = null;
  }, [offlineRole?.image_url, offlineRole?.role]);

  useEffect(() => {
    setRoomImageOk(true);
    roomRoleImageRenderStartedAtRef.current = null;
  }, [roomRole?.image_url, roomRole?.role]);

  useEffect(() => {
    if (!canUseRoomDevTools) {
      setShowRoomDevTools(false);
      setRoomCodeTapCount(0);
    }
  }, [canUseRoomDevTools]);

  useEffect(() => {
    if (roomCodeTapCount <= 0) return;
    const timeout = window.setTimeout(() => setRoomCodeTapCount(0), 1600);
    return () => window.clearTimeout(timeout);
  }, [roomCodeTapCount]);

  useEffect(() => {
    if (offlineRole?.role !== "card" || !offlineRole.image_url || offlineCardImageLoaded) return;
    logImageDebug("card_placeholder_visible_offline", {
      src: resolveImageUrl(offlineRole.image_url),
    });
  }, [apiBase, logImageDebug, offlineCardImageLoaded, offlineRole?.image_url, offlineRole?.role]);

  useEffect(() => {
    if (roomRole?.role !== "card" || !roomRole.image_url || roomCardImageLoaded) return;
    logImageDebug("card_placeholder_visible_room", {
      src: resolveImageUrl(roomRole.image_url),
    });
  }, [apiBase, logImageDebug, roomCardImageLoaded, roomRole?.image_url, roomRole?.role]);

  useEffect(() => {
    if (!roomInfo) {
      prevRoomInfoRef.current = null;
      lastForcedRoomStartToastKeyRef.current = "";
      return;
    }

    const prev = prevRoomInfoRef.current;
    const statusMessage = roomInfo.status_message?.trim();
    if (
      statusMessage &&
      statusMessage !== prev?.status_message &&
      statusMessage.toLowerCase().includes("вышел из комнаты")
    ) {
      pushToast(statusMessage);
    }

    const requiredPlayers = roomInfo.player_limit ?? MIN_PLAYERS;
    const droppedBelowRequired = Boolean(
      prev &&
        (prev.state === "started" || prev.state === "paused") &&
        roomInfo.state === "waiting" &&
        roomInfo.player_count < requiredPlayers
    );
    if (droppedBelowRequired) {
      pushToast("Недостаточно игроков. Ожидаем подключение…");
    }

    prevRoomInfoRef.current = roomInfo;
  }, [roomInfo, pushToast]);

  const activeTurn = useMemo(() => {
    if (
      screen === "offlineTurn" &&
      offlineTurn?.timer_enabled &&
      offlineTurn.turn_state === "turn_loop_active" &&
      offlineTurn.turn_active
    ) {
      return {
        startedAt: offlineTurn.turn_started_at ?? null,
        durationSeconds: offlineTurn.turn_time_seconds ?? null,
        turnsCompleted: false,
      };
    }

    if (
      screen === "roomGame" &&
      roomInfo?.state === "started" &&
      roomInfo.timer_enabled &&
      roomInfo.turn_state === "turn_loop_active" &&
      roomInfo.turn_active
    ) {
      return {
        startedAt: roomInfo.turn_started_at ?? null,
        durationSeconds: roomInfo.turn_time_seconds ?? null,
        turnsCompleted: false,
      };
    }

    return null;
  }, [offlineTurn, roomInfo, screen]);

  useEffect(() => {
    if (!activeTurn || activeTurn.turnsCompleted) {
      setTurnRemainingMs(null);
      return;
    }
    const startedAt = activeTurn.startedAt;
    const durationSeconds = activeTurn.durationSeconds;
    if (!startedAt || !durationSeconds) {
      setTurnRemainingMs(null);
      return;
    }

    const tick = () => {
      const endAtMs = startedAt * 1000 + durationSeconds * 1000;
      const msLeft = Math.max(0, endAtMs - Date.now());
      setTurnRemainingMs(msLeft);
    };

    tick();
    const interval = setInterval(tick, 100);
    return () => clearInterval(interval);
  }, [activeTurn?.durationSeconds, activeTurn?.startedAt, activeTurn?.turnsCompleted]);

  const timerTotalMs = activeTurn?.durationSeconds ? activeTurn.durationSeconds * 1000 : null;
  const timerActive = Boolean(
    timerTotalMs && turnRemainingMs !== null && activeTurn?.startedAt && !activeTurn.turnsCompleted
  );
  const timerProgress =
    timerActive && timerTotalMs
      ? Math.max(0, Math.min(100, ((turnRemainingMs ?? 0) / timerTotalMs) * 100))
      : 0;
  const timerSecondsLeft = turnRemainingMs === null ? null : Math.max(0, Math.ceil(turnRemainingMs / 1000));
  const starterDisplayName = roomInfo?.starter_name ?? roomStarter?.replace("Игру начинает: ", "") ?? null;
  const roomPhase = useMemo<"ready" | "playing" | "paused" | "finished" | "fallback">(() => {
    if (!roomInfo) return "fallback";
    if (roomInfo.state === "paused") return "paused";
    if (roomInfo.turn_state === "ready_to_start") return "ready";
    if (roomInfo.turn_state === "turn_loop_active") return "playing";
    if (roomInfo.turn_state === "finished") return "finished";
    if (roomInfo.state === "started") return "playing";
    return "fallback";
  }, [roomInfo]);
  const roomCurrentTurnName = roomInfo?.current_turn_name ?? `Игрок ${(roomInfo?.current_turn_index ?? 0) + 1}`;
  const roomPlayingTitle = roomInfo?.timer_enabled
    ? `Сейчас ход: ${roomCurrentTurnName}`
    : `Начинает: ${starterDisplayName ?? roomCurrentTurnName}`;

  const clearSessionData = () => {
    leaveSentRef.current = false;
    setPendingOfflineCount(null);
    setOfflineSessionId(null);
    setOfflineTimerEnabled(false);
    setOfflineRole(null);
    setStarterPlayer(null);
    setOfflineTurn(null);
    setRoomInfo(null);
    forceCloseRoomRoleModal();
    setRoomStarter(null);
    setShowRoomDevTools(false);
    setRoomCodeTapCount(0);
    setDevActionLoading(false);
    setRoomCodeInput("");
    setStatus(null);
    setTurnRemainingMs(null);
    setToasts([]);
    prevRoomInfoRef.current = null;
  };

  const resetAll = () => {
    setError(null);
    setFormat(null);
    setGameMode(null);
    setRoomPlayerLimit(null);
    setTimerEnabled(false);
    setTurnTimeSeconds(8);
    clearSessionData();
    setScreen("format");
  };

  const pickFormat = (nextFormat: GameFormat) => {
    clearSessionData();
    setError(null);
    setFormat(nextFormat);
    setGameMode(null);
    setRandomAllowed(DEFAULT_RANDOM_ALLOWED);
    setRoomPlayerLimit(null);
    setTimerEnabled(false);
    setTurnTimeSeconds(8);
    setScreen("playMode");
  };

  const pickStandardMode = () => {
    setError(null);
    setGameMode("standard");
    setRandomAllowed(DEFAULT_RANDOM_ALLOWED);
    setRoomPlayerLimit(null);
    setTimerEnabled(false);
    setTurnTimeSeconds(8);

    if (format === "offline") {
      setPendingOfflineCount(null);
      setScreen("offlinePlayers");
      return;
    }
    setScreen("onlineMenu");
  };

  const pickRandomMode = () => {
    setError(null);
    setGameMode("random");
    setRandomAllowed(DEFAULT_RANDOM_ALLOWED);
    setRoomPlayerLimit(null);
    setTimerEnabled(false);
    setTurnTimeSeconds(8);

    if (format === "offline") {
      setScreen("randomInfo");
      return;
    }
    setScreen("onlineMenu");
  };

  const handleStartOffline = async () => {
    if (!gameMode || !pendingOfflineCount) return;
    setError(null);

    try {
      const res = await api.offlineStart(
        apiConfig,
        gameMode,
        pendingOfflineCount,
        timerEnabled,
        timerEnabled ? turnTimeSeconds : null,
        gameMode === "random" ? randomAllowed : undefined
      );
      setOfflineSessionId(res.session_id);
      setOfflineTimerEnabled(res.timer_enabled);
      setCurrentPlayer(res.current_player_number);
      setOfflineTurn(null);
      setScreen("offlinePlayer");
    } catch (err) {
      setError(toUserError(err, "Не удалось начать игру"));
    }
  };

  const handleReveal = async () => {
    if (!offlineSessionId) return;
    setError(null);

    try {
      const res = await api.offlineReveal(apiConfig, offlineSessionId);
      let cardPreloadOk = true;
      if (res.role === "card" && res.image_url) {
        const preloadResult = await preloadRoleCardImage(res.image_url, "offline_reveal");
        cardPreloadOk = Boolean(preloadResult?.ok);
      }
      offlineRoleImageRenderStartedAtRef.current = performance.now();
      setOfflineCardImageLoaded(res.role === "card" ? cardPreloadOk : true);
      setOfflineRole({
        role: res.role,
        card: res.card,
        image_url: res.image_url,
        elixir_cost: res.elixir_cost,
      });
      setScreen("offlineRole");
    } catch (err) {
      setError(toUserError(err, "Не удалось показать роль"));
    }
  };

  const handleCloseRole = async () => {
    if (!offlineSessionId) return;
    setError(null);

    try {
      const res = await api.offlineClose(apiConfig, offlineSessionId);
      if (!res.finished) {
        if (res.current_player_number) {
          setCurrentPlayer(res.current_player_number);
        }
        setScreen("offlineNext");
        return;
      }

      setStarterPlayer(res.starter_player_number ?? null);

      if (offlineTimerEnabled) {
        const turn = await api.offlineTurnStatus(apiConfig, offlineSessionId);
        setOfflineTurn(turn);
        setScreen("offlineTurn");
        return;
      }

      setScreen("offlineFinished");
    } catch (err) {
      setError(toUserError(err, "Не удалось продолжить"));
    }
  };

  const handleStartOfflineTurn = async () => {
    if (!offlineSessionId) return;
    setError(null);

    try {
      const turn = await api.offlineTurnStart(apiConfig, offlineSessionId);
      setOfflineTurn(turn);
    } catch (err) {
      setError(toUserError(err, GENERIC_ERROR_MESSAGE));
    }
  };

  const handleFinishOfflineTurn = async () => {
    if (!offlineSessionId) return;
    setError(null);

    try {
      const turn = await api.offlineTurnFinish(apiConfig, offlineSessionId);
      setOfflineTurn(turn);
    } catch (err) {
      setError(toUserError(err, GENERIC_ERROR_MESSAGE));
    }
  };

  const handleRestartOffline = async () => {
    if (!offlineSessionId) return;
    setError(null);
    setStatus("Новая игра начинается…");

    try {
      const res = await api.offlineRestart(apiConfig, offlineSessionId);
      setOfflineSessionId(res.session_id);
      setOfflineTimerEnabled(res.timer_enabled);
      setCurrentPlayer(res.current_player_number);
      setOfflineRole(null);
      setStarterPlayer(null);
      setOfflineTurn(null);
      setStatus(null);
      setScreen("offlinePlayer");
    } catch (err) {
      setStatus(null);
      setError(toUserError(err, "Не удалось перезапустить игру"));
    }
  };

  const handleProceedRandomRoomSettings = () => {
    if (format !== "online" || gameMode !== "random") {
      setError("Сначала выбери формат и режим");
      return;
    }
    if (roomPlayerLimit === null || roomPlayerLimit < MIN_PLAYERS || roomPlayerLimit > MAX_PLAYERS) {
      setError("Выберите корректный лимит игроков");
      return;
    }
    setError(null);
    setScreen("roomCreateRandomSettings");
  };

  const createRoomNow = async () => {
    if (format !== "online" || !gameMode) {
      setError("Сначала выбери формат и режим");
      return;
    }
    if (roomPlayerLimit === null || roomPlayerLimit < MIN_PLAYERS || roomPlayerLimit > MAX_PLAYERS) {
      setError("Выберите корректный лимит игроков");
      return;
    }
    if (gameMode === "random" && randomAllowed.length < 2) {
      setError("Выберите минимум два режима");
      return;
    }

    setError(null);
    if (ROOM_DEV_LOGS) {
      console.info("[room_debug] create request", {
        baseUrl: apiBase || "(same-origin)",
        endpoint: `${apiBase || ""}/api/room/create`,
        gameMode,
        playerLimit: roomPlayerLimit,
      });
    }

    try {
      const info = await api.roomCreate(
        apiConfig,
        format,
        gameMode,
        roomPlayerLimit,
        timerEnabled,
        timerEnabled ? turnTimeSeconds : null,
        gameMode === "random" ? randomAllowed : undefined
      );
      setRoomInfo(info);
      setRoomStarter(null);
      setShowRoomDevTools(false);
      setRoomCodeTapCount(0);
      setScreen("room");
    } catch (err) {
      setError(toUserError(err, "Не удалось создать комнату"));
    }
  };

  const handleJoinRoom = async () => {
    const normalizedCode = normalizeRoomCode(roomCodeInput);
    if (!normalizedCode) {
      setError("Введите корректный код комнаты");
      return;
    }
    if (format !== "online") {
      setError("Сначала выбери формат и режим");
      return;
    }

    setError(null);
    if (ROOM_DEV_LOGS) {
      console.info("[room_debug] join request", {
        baseUrl: apiBase || "(same-origin)",
        endpoint: `${apiBase || ""}/api/room/join`,
        rawCode: roomCodeInput,
        normalizedCode,
      });
    }

    try {
      const info = await api.roomJoin(apiConfig, normalizedCode);
      setRoomInfo(info);
      setGameMode(info.play_mode);
      setRoomStarter(null);
      setShowRoomDevTools(false);
      setRoomCodeTapCount(0);
      setRoomCodeInput(normalizedCode);
      setScreen(info.state === "waiting" ? "room" : "roomGame");
    } catch (err) {
      setError(toUserError(err, "Не удалось подключиться"));
    }
  };

  const handleStartRoom = async () => {
    if (!roomInfo) return;
    setError(null);
    setStatus(null);

    try {
      const res = await api.roomStart(apiConfig, roomInfo.room_code);
      setRoomStarter(`Игру начинает: ${res.starter_name}`);
      const info = await api.roomStatus(apiConfig, roomInfo.room_code);
      setRoomInfo(info);
      setShowRoomDevTools(false);
      setScreen("roomGame");
    } catch (err) {
      setError(toUserError(err, "Не удалось начать игру"));
    }
  };

  const handleStartRoomTurn = async () => {
    if (!roomInfo) return;
    setError(null);

    try {
      const info = await api.roomTurnStart(apiConfig, roomInfo.room_code);
      setRoomInfo(info);
    } catch (err) {
      setError(toUserError(err, GENERIC_ERROR_MESSAGE));
    }
  };

  const handleFinishRoomTurn = async () => {
    if (!roomInfo) return;
    setError(null);

    try {
      const info = await api.roomTurnFinish(apiConfig, roomInfo.room_code);
      setRoomInfo(info);
    } catch (err) {
      setError(toUserError(err, GENERIC_ERROR_MESSAGE));
    }
  };

  const handleResumeRoom = async () => {
    if (!roomInfo) return;
    setError(null);

    try {
      const info = await api.roomResume(apiConfig, roomInfo.room_code);
      setRoomInfo(info);
    } catch (err) {
      setError(toUserError(err, GENERIC_ERROR_MESSAGE));
    }
  };

  const handleLeaveRoom = async () => {
    if (!roomInfo) return;
    const ok = window.confirm("Точно ли вы хотите выйти?");
    if (!ok) return;

    try {
      await api.roomLeave(apiConfig, roomInfo.room_code);
    } catch {
      // ignore leave errors and close local session
    } finally {
      resetAll();
    }
  };

  const handleLobbyCodeTap = () => {
    if (!canUseRoomPreviewTools) return;
    setRoomCodeTapCount((prev) => {
      const next = prev + 1;
      if (next >= 5) {
        setShowRoomDevTools(true);
        return 0;
      }
      return next;
    });
  };

  const runRoomDevAction = async (action: () => Promise<RoomInfo>) => {
    if (!canUseRoomDevTools || !roomInfo) return;
    setError(null);
    setDevActionLoading(true);
    try {
      const updatedRoom = await action();
      setRoomInfo(updatedRoom);
    } catch (err) {
      setError(toUserError(err, GENERIC_ERROR_MESSAGE));
    } finally {
      setDevActionLoading(false);
    }
  };

  const handleRoomAddBots = async (count: number) => {
    if (!roomInfo) return;
    await runRoomDevAction(() => api.roomBotsAdd(apiConfig, roomInfo.room_code, count));
  };

  const handleRoomFillBots = async () => {
    if (!roomInfo) return;
    await runRoomDevAction(() => api.roomBotsFill(apiConfig, roomInfo.room_code));
  };

  const handleRoomClearBots = async () => {
    if (!roomInfo) return;
    await runRoomDevAction(() => api.roomBotsClear(apiConfig, roomInfo.room_code));
  };

  const handleDevPreviewCard = async (cardName: string) => {
    if (!canUseRoomPreviewTools) return;
    setError(null);
    setDevActionLoading(true);
    try {
      const cardMeta = await fetchCardMeta(cardName);
      let cardPreloadOk = true;
      if (cardMeta.image_url) {
        const preloadResult = await preloadRoleCardImage(cardMeta.image_url, "dev_card_preview");
        cardPreloadOk = Boolean(preloadResult?.ok);
      }
      roomRoleImageRenderStartedAtRef.current = performance.now();
      setRoomImageOk(cardPreloadOk);
      setRoomCardImageLoaded(cardMeta.image_url ? cardPreloadOk : true);
      openRoomRoleModal({
        role: "card",
        card: cardMeta.name,
        image_url: cardMeta.image_url ?? undefined,
        elixir_cost: cardMeta.elixir_cost ?? null,
      });
      setShowRoomDevTools(false);
    } catch (err) {
      setError(toUserError(err, "Не удалось показать карту"));
    } finally {
      setDevActionLoading(false);
    }
  };

  const handleRestartRoom = async () => {
    if (!roomInfo) return;
    setError(null);
    setStatus("Новая игра начинается…");

    try {
      const res = await api.roomRestart(apiConfig, roomInfo.room_code);
      setRoomStarter(`Игру начинает: ${res.starter_name}`);
      const info = await api.roomStatus(apiConfig, roomInfo.room_code);
      setRoomInfo(info);
      setShowRoomDevTools(false);
      setStatus(null);
      setScreen("roomGame");
    } catch (err) {
      setStatus(null);
      setError(toUserError(err, "Не удалось перезапустить игру"));
    }
  };

  const handleReturnRoomToLobby = async () => {
    if (!roomInfo) return;
    setError(null);
    setStatus(null);

    try {
      const info = await api.roomToLobby(apiConfig, roomInfo.room_code);
      setRoomInfo(info);
      setRoomStarter(null);
      setScreen("room");
    } catch (err) {
      setError(toUserError(err, GENERIC_ERROR_MESSAGE));
    }
  };

  const handleGetRole = async () => {
    if (!roomInfo) return;
    setError(null);

    try {
      const res = await api.roomRole(apiConfig, roomInfo.room_code);
      let cardPreloadOk = true;
      if (res.role === "card" && res.image_url) {
        const preloadResult = await preloadRoleCardImage(res.image_url, "room_role");
        cardPreloadOk = Boolean(preloadResult?.ok);
      }
      roomRoleImageRenderStartedAtRef.current = performance.now();
      setRoomCardImageLoaded(res.role === "card" ? cardPreloadOk : true);
      openRoomRoleModal({
        role: res.role,
        card: res.card,
        image_url: res.image_url,
        elixir_cost: res.elixir_cost,
      });
    } catch (err) {
      setError(toUserError(err, "Не удалось получить роль"));
    }
  };

  const backFromJoin = () => {
    if (!gameMode) {
      setScreen("playMode");
      return;
    }
    setScreen("onlineMenu");
  };

  const showTopBackButton =
    screen === "playMode" ||
    screen === "randomInfo" ||
    screen === "onlineMenu" ||
    screen === "roomCreateSettings" ||
    screen === "roomCreateRandomSettings" ||
    screen === "offlinePlayers" ||
    screen === "joinRoom";

  const handleTopBack = () => {
    if (screen === "playMode") {
      resetAll();
      return;
    }
    if (screen === "randomInfo" || screen === "offlinePlayers" || screen === "onlineMenu") {
      setScreen("playMode");
      return;
    }
    if (screen === "roomCreateSettings") {
      setScreen("onlineMenu");
      return;
    }
    if (screen === "roomCreateRandomSettings") {
      setScreen("roomCreateSettings");
      return;
    }
    if (screen === "joinRoom") {
      backFromJoin();
    }
  };

  const renderTurnProgress = () => {
    if (!timerActive || timerSecondsLeft === null) return null;

    return (
      <div className="timer">
        <div className="timer-meta">
          <span>Осталось времени на ход</span>
          {timerSecondsLeft === 0 ? (
            <span className="timer-ended">Время вышло</span>
          ) : (
            <span className="timer-value">{timerSecondsLeft} сек</span>
          )}
        </div>
        <div className="timer-bar">
          <div className="timer-fill" style={{ width: `${timerProgress}%` }} />
        </div>
      </div>
    );
  };

  const renderTimerSetup = (options?: { title?: string; checkboxLabel?: string }) => (
    <div className="timer-options">
      {options?.title && <div className="settings-label">{options.title}</div>}
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={timerEnabled}
          onChange={(e) => setTimerEnabled(e.target.checked)}
        />
        <span>{options?.checkboxLabel ?? "Использовать таймер"}</span>
      </label>

      {timerEnabled && (
        <div className="timer-setup">
          <div className="timer-setup-label">Выберите, сколько времени даётся каждому игроку на ход</div>
          <div className="timer-setup-value">{turnTimeSeconds} секунд</div>
          <input
            className="timer-slider"
            type="range"
            min={5}
            max={30}
            step={1}
            value={turnTimeSeconds}
            onChange={(e) => setTurnTimeSeconds(Number(e.target.value))}
          />
          <div className="timer-setup-range">5–30 сек</div>
        </div>
      )}
    </div>
  );

  const isHome = screen === "format";

  return (
    <div className="app">
      <div className="app-bg-placeholder" />
      <div
        className={`app-bg-layer ${backgroundReady ? "is-ready" : ""} ${
          assetsReady ? "assets-ready" : "assets-loading"
        }`}
        style={{ backgroundImage: `url("${displayedBackgroundUrl}")` }}
      />
      <div className="screenOverlay" />
      <div className={`screenContent ${isHome ? "homeContent" : "gameContent"}`}>
        {isHome && (
          <>
            <div className="homeHeroBanner" aria-label="Баннер Clash Royale Шпион">
              {!homeBannerLoadFailed ? (
                <img
                  src={HOME_HERO_BANNER_URL}
                  alt="Clash Royale Шпион"
                  loading="eager"
                  onError={() => setHomeBannerLoadFailed(true)}
                />
              ) : (
                <div className="homeHeroFallback">Clash Royale Шпион</div>
              )}
            </div>

            {error && <div className="error">{error}</div>}
            {status && <div className="hint status">{status}</div>}

            <div className="homeActions">
              <div className="homeText">
                Выбери формат игры
                <span>Офлайн — один телефон. Онлайн — каждый игрок у себя.</span>
              </div>
              <button className="btn full with-icon" onClick={() => pickFormat("offline")}>
                <span className="btn-icon" aria-hidden="true">
                  <IconOffline />
                </span>
                <span>Офлайн</span>
              </button>
              <button className="btn secondary full with-icon" onClick={() => pickFormat("online")}>
                <span className="btn-icon" aria-hidden="true">
                  <IconOnline />
                </span>
                <span>Онлайн</span>
              </button>
            </div>
          </>
        )}

        {!isHome && (
          <>
            <header className="header">
              <div className="logo">Clash Royale Шпион</div>
              {showTopBackButton && (
                <button className="top-back-btn" onClick={handleTopBack}>
                  ← Назад
                </button>
              )}
            </header>

            {toasts.length > 0 && (
              <div className="toast-stack" role="status" aria-live="polite">
                {toasts.map((toast) => (
                  <div key={toast.id} className="toast-item">
                    {toast.text}
                  </div>
                ))}
              </div>
            )}

            {error && <div className="error">{error}</div>}
            {status && <div className="hint status">{status}</div>}

            {screen === "loading" && (
              <div className="card">
                <div className="title">Подготовка...</div>
              </div>
            )}

            {screen === "playMode" && (
              <div className="card center play-mode-card">
                <div className="title">Выбери режим</div>
                <div className="mode-preview" aria-hidden="true">
                  <img className="mode-preview-art" src={SPY_IMAGE_URL} alt="" loading="eager" />
                </div>
                <div className="actions stack">
                  <button className="btn full" onClick={pickStandardMode}>
                    Стандартный
                  </button>
                  <button className="btn secondary full" onClick={pickRandomMode}>
                    Рандом
                  </button>
                </div>
              </div>
            )}

            {screen === "randomInfo" && format === "offline" && (
              <div className="card center">
                <div className="title">Рандом режим</div>
                <p className="text">
                  Отметьте режимы, которые могут выпасть. Один из них будет выбран случайно.
                </p>

                <div className="randomList">
                  {RANDOM_SCENARIOS.map((scenario) => {
                    const checked = randomAllowed.includes(scenario.id);
                    return (
                      <button
                        key={scenario.id}
                        type="button"
                        className={`randomItem ${checked ? "checked" : ""}`}
                        onClick={() => {
                          setRandomAllowed((prev) => {
                            if (prev.includes(scenario.id)) {
                              return prev.filter((item) => item !== scenario.id);
                            }
                            return [...prev, scenario.id];
                          });
                        }}
                      >
                        <span className={`checkbox ${checked ? "checked" : ""}`} />
                        <span className="randomLabel">{scenario.label}</span>
                      </button>
                    );
                  })}
                </div>

                {randomAllowed.length < 2 && <div className="hint danger">Выберите минимум два режима</div>}

                <div className="actions stack">
                  <button
                    className="btn full"
                    onClick={() => {
                      setPendingOfflineCount(null);
                      setScreen("offlinePlayers");
                    }}
                    disabled={randomAllowed.length < 2}
                  >
                    Продолжить
                  </button>
                </div>
              </div>
            )}

            {screen === "onlineMenu" && format === "online" && gameMode && (
              <div className="card center online-menu-card">
                <div className="title">
                  Онлайн режим: {gameMode === "standard" ? "Стандартный" : "Рандом"}
                </div>
                <p className="text">Выберите, что хотите сделать.</p>
                <div className="actions stack online-menu-actions">
                  <button
                    className="btn full with-icon"
                    onClick={() => {
                      setRoomPlayerLimit(null);
                      setScreen("roomCreateSettings");
                    }}
                  >
                    <span className="btn-icon" aria-hidden="true">
                      <IconCreateRoom />
                    </span>
                    <span>Создать комнату</span>
                  </button>
                  <button className="btn secondary full with-icon" onClick={() => setScreen("joinRoom")}>
                    <span className="btn-icon" aria-hidden="true">
                      <IconJoinRoom />
                    </span>
                    <span>Подключиться</span>
                  </button>
                </div>
              </div>
            )}

            {screen === "roomCreateSettings" && format === "online" && gameMode && (
              <div className="card center">
                <div className="title">Настройки комнаты</div>
                <p className="text">
                  {gameMode === "random"
                    ? "Шаг 1 из 2: выберите лимит игроков."
                    : "Выберите лимит игроков, затем дополнительные параметры."}
                </p>

                <div className="settings-block">
                  <div className="settings-label">Лимит игроков в комнате</div>
                  <div className="grid">
                    {Array.from({ length: MAX_PLAYERS - MIN_PLAYERS + 1 }, (_, i) => i + MIN_PLAYERS).map(
                      (count) => (
                        <button
                          key={count}
                          type="button"
                          className={`btn small ${roomPlayerLimit === count ? "secondary" : ""}`}
                          onClick={() => setRoomPlayerLimit(count)}
                        >
                          {count}
                        </button>
                      )
                    )}
                  </div>
                  {roomPlayerLimit === null && <div className="hint">Сначала выберите лимит игроков</div>}
                </div>

                {gameMode !== "random" && renderTimerSetup()}

                <div className="actions stack">
                  {gameMode === "random" ? (
                    <button
                      className="btn full"
                      onClick={handleProceedRandomRoomSettings}
                      disabled={roomPlayerLimit === null}
                    >
                      Далее
                    </button>
                  ) : (
                    <button className="btn full" onClick={createRoomNow} disabled={roomPlayerLimit === null}>
                      Создать
                    </button>
                  )}
                </div>
              </div>
            )}

            {screen === "roomCreateRandomSettings" && format === "online" && gameMode === "random" && (
              <div className="card center">
                <div className="title">Сценарии и таймер</div>
                <p className="text">Шаг 2 из 2: выберите сценарии, затем при необходимости включите таймер.</p>

                <div className="settings-block">
                  <div className="settings-label">Сценарии рандома</div>
                  <div className="randomList">
                    {RANDOM_SCENARIOS.map((scenario) => {
                      const checked = randomAllowed.includes(scenario.id);
                      return (
                        <button
                          key={scenario.id}
                          type="button"
                          className={`randomItem ${checked ? "checked" : ""}`}
                          onClick={() => {
                            setRandomAllowed((prev) => {
                              if (prev.includes(scenario.id)) {
                                return prev.filter((item) => item !== scenario.id);
                              }
                              return [...prev, scenario.id];
                            });
                          }}
                        >
                          <span className={`checkbox ${checked ? "checked" : ""}`} />
                          <span className="randomLabel">{scenario.label}</span>
                        </button>
                      );
                    })}
                  </div>
                  {randomAllowed.length < 2 && <div className="hint danger">Выберите минимум два режима</div>}
                </div>

                {renderTimerSetup({ title: "Таймер", checkboxLabel: "Включить таймер" })}

                <div className="actions stack">
                  <button
                    className="btn full"
                    onClick={createRoomNow}
                    disabled={roomPlayerLimit === null || randomAllowed.length < 2}
                  >
                    Создать
                  </button>
                </div>
              </div>
            )}

            {screen === "offlinePlayers" && (
              <div className="card center">
                <div className="title">Сколько игроков?</div>
                <div className="grid">
                  {Array.from({ length: 10 }, (_, i) => i + 3).map((count) => (
                    <button
                      key={count}
                      className={`btn small ${pendingOfflineCount === count ? "secondary" : ""}`}
                      onClick={() => setPendingOfflineCount(count)}
                    >
                      {count}
                    </button>
                  ))}
                </div>

                {pendingOfflineCount && <div className="hint">Выбрано игроков: {pendingOfflineCount}</div>}

                {renderTimerSetup()}

                <div className="actions stack">
                  <button className="btn full" onClick={handleStartOffline} disabled={!pendingOfflineCount}>
                    Начать игру
                  </button>
                </div>
              </div>
            )}

            {screen === "offlinePlayer" && (
              <div className="card center">
                <div className="title">Игрок {currentPlayer}</div>
                <p className="text">Нажми кнопку, чтобы увидеть свою карту.</p>
                <div className="actions">
                  <button className="btn" onClick={handleReveal}>
                    Показать карту
                  </button>
                </div>
              </div>
            )}

            {screen === "offlineRole" && offlineRole && (
              <div className="card center">
                <div className="title">Твоя роль</div>
                {offlineRole.role === "spy" && (
                  <div className="card-image spy-frame">
                    <img className="spy-art" src={SPY_IMAGE_URL} alt="Шпион" />
                  </div>
                )}
                {offlineRole.role === "card" && offlineRole.image_url && offlineImageOk && (
                  <div className="card-image-wrapper">
                    {!offlineCardImageLoaded && <div className="card-image-placeholder" aria-hidden />}
                    <img
                      className={`card-image ${offlineCardImageLoaded ? "is-loaded" : "is-loading"}`}
                      src={resolveImageUrl(offlineRole.image_url)}
                      alt="Карта"
                      loading="eager"
                      decoding="async"
                      onLoad={(event) => handleOfflineCardImageLoad(event.currentTarget.currentSrc || event.currentTarget.src)}
                      onError={(event) => {
                        setOfflineImageOk(false);
                        setOfflineCardImageLoaded(false);
                        logImageDebug("card_render_error_offline", {
                          src: event.currentTarget.currentSrc || event.currentTarget.src,
                        });
                      }}
                    />
                    {typeof offlineRole.elixir_cost === "number" && (
                      <div className="elixir-badge" aria-label={`Эликсир ${offlineRole.elixir_cost}`}>
                        <img src={ELIXIR_IMAGE_URL} alt="Эликсир" />
                        <span>{offlineRole.elixir_cost}</span>
                      </div>
                    )}
                  </div>
                )}
                {offlineRole.role === "card" && offlineRole.image_url && !offlineImageOk && (
                  <div className="hint">Изображение недоступно</div>
                )}
                <div className="role">{offlineRole.role === "spy" ? "Ты шпион" : `Карта: ${offlineRole.card}`}</div>
                <div className="actions">
                  <button className="btn" onClick={handleCloseRole}>
                    Закрыть
                  </button>
                </div>
              </div>
            )}

            {screen === "offlineNext" && (
              <div className="card center">
                <div className="title">Передайте телефон следующему игроку</div>
                <p className="text">Когда будете готовы, продолжайте.</p>
                <div className="actions">
                  <button className="btn" onClick={() => setScreen("offlinePlayer")}>
                    Продолжить
                  </button>
                </div>
              </div>
            )}

            {screen === "offlineFinished" && (
              <div className="card center">
                <div className="title">Роли розданы</div>
                <p className="text">Игру начинает: Игрок {starterPlayer ?? "?"}</p>
                <div className="actions stack">
                  <button className="btn full" onClick={handleRestartOffline}>
                    Сыграть ещё
                  </button>
                  <button className="btn secondary full" onClick={resetAll}>
                    Новая игра
                  </button>
                </div>
              </div>
            )}

            {screen === "offlineTurn" && offlineTurn && (
              <div className="card center turn-board">
                {offlineTurn.turn_state === "ready_to_start" && (
                  <>
                    <div className="title">Роли розданы</div>
                    <p className="text">Игру начинает: Игрок {starterPlayer ?? offlineTurn.current_player_number}</p>
                    <div className="actions">
                      <button className="btn" onClick={handleStartOfflineTurn}>
                        Начать игру
                      </button>
                    </div>
                  </>
                )}

                {offlineTurn.turn_state === "turn_loop_active" && (
                  <>
                    <div className="title">Ход: Игрок {offlineTurn.current_player_number}</div>
                    <p className="text">Переход к следующему игроку происходит автоматически по таймеру.</p>
                    {renderTurnProgress()}
                    <div className="actions">
                      <button className="btn secondary" onClick={handleFinishOfflineTurn}>
                        Игра окончена
                      </button>
                    </div>
                  </>
                )}

                {offlineTurn.turn_state === "finished" && (
                  <>
                    <div className="title">Игра завершена</div>
                    <p className="text">Можно начать новый раунд или вернуться в меню.</p>
                    <div className="actions stack">
                      <button className="btn full" onClick={handleRestartOffline}>
                        Сыграть ещё
                      </button>
                      <button className="btn secondary full" onClick={resetAll}>
                        Новая игра
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}

            {screen === "joinRoom" && (
              <div className="card center">
                <div className="title">Подключиться</div>
                <input
                  className="input"
                  placeholder="Код комнаты"
                  value={roomCodeInput}
                  onChange={(e) => setRoomCodeInput(e.target.value)}
                />
                <div className="actions stack">
                  <button className="btn full" onClick={handleJoinRoom}>
                    Подключиться
                  </button>
                </div>
              </div>
            )}

            {screen === "room" && roomInfo && (
              <div className="card center room-lobby-card">
                <div className="title">
                  Код комнаты:{" "}
                  <button type="button" className="room-code-button" onClick={handleLobbyCodeTap}>
                    <span className="room-code">{roomInfo.room_code}</span>
                  </button>
                </div>

                <div className="players">
                  {roomInfo.players.map((player) => (
                    <div key={player.user_id} className="player player-row">
                      <span>{renderPlayerName(player)}</span>
                      {String(player.user_id) === String(roomInfo.owner_user_id) && <span className="host-badge">хост</span>}
                    </div>
                  ))}
                </div>
                <div className="lobby-counter">
                  {roomInfo.player_count} / {roomInfo.player_limit ?? MAX_PLAYERS}
                </div>
                {roomInfo.you_are_owner ? (
                  roomInfo.player_count < (roomInfo.player_limit ?? MAX_PLAYERS) && (
                    <div className="lobby-helper">
                      Поделитесь кодом для подключения
                      <br />
                      Ожидаем игроков
                    </div>
                  )
                ) : (
                  <div className="lobby-helper">Ожидаем игроков</div>
                )}

                {roomInfo.can_start && (
                  <div className="actions">
                    <button className="btn" onClick={handleStartRoom}>
                      Начать игру
                    </button>
                  </div>
                )}

                {canUseRoomDevTools && (
                  <button
                    type="button"
                    className="dev-tools-trigger"
                    aria-label="Открыть DEV панель"
                    onClick={() => setShowRoomDevTools(true)}
                  >
                    ⋯
                  </button>
                )}
                <button className="leave-link" onClick={handleLeaveRoom}>
                  Выйти из комнаты
                </button>
              </div>
            )}

            {showRoomDevTools && canUseRoomPreviewTools && roomInfo && (
              <div className="dev-modal-backdrop" onClick={() => !devActionLoading && setShowRoomDevTools(false)}>
                <div className="dev-modal" onClick={(e) => e.stopPropagation()}>
                  <div className="title">DEV инструменты</div>
                  <p className="text">Скрытые инструменты для тестирования в лобби.</p>
                  <div className="actions stack">
                    {canUseRoomDevTools && (
                      <button className="btn full" onClick={() => handleRoomAddBots(1)} disabled={devActionLoading}>
                        Добавить бота +1
                      </button>
                    )}
                    {canUseRoomDevTools && (
                      <button className="btn full" onClick={() => handleRoomAddBots(3)} disabled={devActionLoading}>
                        Добавить 3 бота
                      </button>
                    )}
                    {canUseRoomDevTools && (
                      <button className="btn full" onClick={handleRoomFillBots} disabled={devActionLoading}>
                        Заполнить до лимита
                      </button>
                    )}
                    {canUseRoomDevTools && (
                      <button className="btn secondary full" onClick={handleRoomClearBots} disabled={devActionLoading}>
                        Удалить всех ботов
                      </button>
                    )}
                    <button
                      className="btn secondary full"
                      onClick={() => handleDevPreviewCard("Королевский гигант")}
                      disabled={devActionLoading}
                    >
                      Карта: Королевский гигант
                    </button>
                    <button
                      className="btn secondary full"
                      onClick={() => handleDevPreviewCard("Электрогигант")}
                      disabled={devActionLoading}
                    >
                      Карта: Электрогигант
                    </button>
                    <button
                      className="link"
                      type="button"
                      onClick={() => setShowRoomDevTools(false)}
                      disabled={devActionLoading}
                    >
                      Закрыть
                    </button>
                  </div>
                </div>
              </div>
            )}

            {screen === "roomGame" && roomInfo && (
              <div className={`card center room-game-card room-phase-${roomPhase}`}>
                {roomPhase === "ready" && (
                  <>
                    <div className="room-phase-title">Начинает: {starterDisplayName ?? "—"}</div>
                    <div className="actions stack">
                      <button className="btn full with-icon" onClick={handleGetRole}>
                        <span className="btn-icon" aria-hidden="true">
                          <IconShowCard />
                        </span>
                        <span>Показать карту</span>
                      </button>
                      {roomInfo.you_are_owner && (
                        <button className="btn secondary full with-icon" onClick={handleStartRoomTurn}>
                          <span className="btn-icon" aria-hidden="true">
                            <IconStart />
                          </span>
                          <span>Начать игру</span>
                        </button>
                      )}
                    </div>
                    {!roomInfo.you_are_owner && (
                      <div className="hint">Ждём начала игры от {roomInfo.host_name || roomInfo.owner_name}</div>
                    )}
                  </>
                )}

                {(roomPhase === "playing" || roomPhase === "paused") && (
                  <>
                    <div className="room-phase-title">{roomPlayingTitle}</div>
                    {roomInfo.timer_enabled && renderTurnProgress()}
                    {roomInfo.state === "paused" && (
                      <div className="hint danger">Игра на паузе. Таймер остановлен.</div>
                    )}

                    <div className="actions stack">
                      <button className="btn full with-icon" onClick={handleGetRole}>
                        <span className="btn-icon" aria-hidden="true">
                          <IconShowCard />
                        </span>
                        <span>Показать карту</span>
                      </button>

                      {roomInfo.you_are_owner && roomPhase === "paused" && (
                        <button className="btn full" onClick={handleResumeRoom}>
                          Продолжить игру
                        </button>
                      )}

                      {roomInfo.you_are_owner && roomPhase === "playing" && (
                        <button className="btn secondary full" onClick={handleFinishRoomTurn}>
                          Игра окончена
                        </button>
                      )}
                    </div>

                    <button className="leave-link" onClick={handleLeaveRoom}>
                      {roomInfo.you_are_owner ? "Выйти из лобби" : "Выйти из комнаты"}
                    </button>
                  </>
                )}

                {roomPhase === "finished" && (
                  <>
                    <div className="room-phase-title">Игра окончена</div>
                    {roomInfo.you_are_owner ? (
                      <div className="actions stack">
                        <button className="btn full" onClick={handleRestartRoom}>
                          Сыграть ещё
                        </button>
                        <button className="btn secondary full" onClick={handleReturnRoomToLobby}>
                          Новая игра
                        </button>
                      </div>
                    ) : (
                      <>
                        <div className="hint">Ожидаем действий хоста</div>
                        <button className="leave-link" onClick={handleLeaveRoom}>
                          Выйти из комнаты
                        </button>
                      </>
                    )}
                  </>
                )}

                {roomPhase === "fallback" && (
                  <>
                    <div className="room-phase-title">Игра запущена</div>
                    <div className="actions stack">
                      <button className="btn full with-icon" onClick={handleGetRole}>
                        <span className="btn-icon" aria-hidden="true">
                          <IconShowCard />
                        </span>
                        <span>Показать карту</span>
                      </button>
                    </div>
                    <button className="leave-link" onClick={handleLeaveRoom}>
                      {roomInfo.you_are_owner ? "Выйти из лобби" : "Выйти из комнаты"}
                    </button>
                  </>
                )}
              </div>
            )}

            {(screen === "roomGame" || screen === "room") && isRoomRoleMounted && roomRole && (
              <div className={`role-modal-backdrop ${isRoomRoleOpen ? "is-open" : ""}`} onClick={closeRoomRoleModal}>
                <div className="card role-modal-card" onClick={(event) => event.stopPropagation()}>
                  <div className="title">Твоя роль</div>
                  {roomRole.role === "spy" && (
                    <div className="card-image spy-frame">
                      <img className="spy-art" src={SPY_IMAGE_URL} alt="Шпион" />
                    </div>
                  )}
                  {roomRole.role === "card" && roomRole.image_url && roomImageOk && (
                    <div className="card-image-wrapper">
                      {!roomCardImageLoaded && <div className="card-image-placeholder" aria-hidden />}
                      <img
                        className={`card-image ${roomCardImageLoaded ? "is-loaded" : "is-loading"}`}
                        src={resolveImageUrl(roomRole.image_url)}
                        alt="Карта"
                        loading="eager"
                        decoding="async"
                        onLoad={(event) => handleRoomCardImageLoad(event.currentTarget.currentSrc || event.currentTarget.src)}
                        onError={(event) => {
                          setRoomImageOk(false);
                          setRoomCardImageLoaded(false);
                          logImageDebug("card_render_error_room", {
                            src: event.currentTarget.currentSrc || event.currentTarget.src,
                          });
                        }}
                      />
                      {typeof roomRole.elixir_cost === "number" && (
                        <div className="elixir-badge" aria-label={`Эликсир ${roomRole.elixir_cost}`}>
                          <img src={ELIXIR_IMAGE_URL} alt="Эликсир" />
                          <span>{roomRole.elixir_cost}</span>
                        </div>
                      )}
                    </div>
                  )}
                  {roomRole.role === "card" && roomRole.image_url && !roomImageOk && (
                    <div className="hint">Изображение недоступно</div>
                  )}
                  <div className="role">{roomRole.role === "spy" ? "Ты шпион" : `Карта: ${roomRole.card}`}</div>
                  <div className="actions">
                    <button className="btn" onClick={closeRoomRoleModal}>
                      Закрыть
                    </button>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
