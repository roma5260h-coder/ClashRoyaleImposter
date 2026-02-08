import React, { useEffect, useMemo, useRef, useState } from "react";
import { api, type ApiConfig } from "./api";
import type { GameFormat, GameMode, RoomInfo, TurnState } from "./types";

const tg = (window as any).Telegram?.WebApp;

type Screen =
  | "loading"
  | "format"
  | "playMode"
  | "randomInfo"
  | "onlineMenu"
  | "roomCreateSettings"
  | "offlinePlayers"
  | "offlinePlayer"
  | "offlineRole"
  | "offlineNext"
  | "offlineFinished"
  | "offlineTurn"
  | "joinRoom"
  | "room"
  | "roomGame"
  | "roomRole";

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

const MIN_PLAYERS = 3;
const MAX_PLAYERS = 12;
const GENERIC_ERROR_MESSAGE = "Произошла ошибка, попробуйте ещё раз";
const RANDOM_SCENARIOS = [
  { id: "all_spies", label: "Все шпионы" },
  { id: "same_card", label: "У всех одна карта" },
  { id: "different_cards", label: "У всех разные карты" },
  { id: "multi_spy", label: "Несколько шпионов" },
];

const DEFAULT_RANDOM_ALLOWED = RANDOM_SCENARIOS.map((scenario) => scenario.id);

function toUserError(err: unknown, fallback: string): string {
  if (err instanceof Error && err.message) {
    return err.message;
  }
  return fallback;
}

export default function App() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [format, setFormat] = useState<GameFormat | null>(null);
  const [gameMode, setGameMode] = useState<GameMode | null>(null);
  const [randomAllowed, setRandomAllowed] = useState<string[]>(DEFAULT_RANDOM_ALLOWED);
  const [roomPlayerLimit, setRoomPlayerLimit] = useState<number>(MAX_PLAYERS);

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
  const [starterPlayer, setStarterPlayer] = useState<number | null>(null);
  const [offlineTurn, setOfflineTurn] = useState<OfflineTurnStatus | null>(null);

  const [roomInfo, setRoomInfo] = useState<RoomInfo | null>(null);
  const [roomCodeInput, setRoomCodeInput] = useState<string>("");
  const [roomRole, setRoomRole] = useState<{
    role: string;
    card?: string;
    image_url?: string;
    elixir_cost?: number | null;
  } | null>(null);
  const [roomImageOk, setRoomImageOk] = useState<boolean>(true);
  const [roomStarter, setRoomStarter] = useState<string | null>(null);
  const leaveSentRef = useRef<boolean>(false);

  const [turnRemainingMs, setTurnRemainingMs] = useState<number | null>(null);

  const [initData, setInitData] = useState<string>(() => tg?.initData ?? "");
  const apiBase = import.meta.env.VITE_API_BASE ?? "";

  const resolveImageUrl = (url: string) => {
    if (/^https?:\/\//i.test(url)) return url;
    if (!apiBase) return url;
    const trimmed = apiBase.replace(/\/$/, "");
    return `${trimmed}${url.startsWith("/") ? "" : "/"}${url}`;
  };

  const apiConfig: ApiConfig = useMemo(() => ({ baseUrl: apiBase, initData }), [apiBase, initData]);

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
    if (!roomInfo || (screen !== "room" && screen !== "roomGame" && screen !== "roomRole")) return;

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
        if (screen === "room" && (info.state === "started" || info.state === "paused")) {
          setScreen("roomGame");
        }
      } catch {
        // ignore transient polling errors
      }
    };

    poll();
    const interval = setInterval(poll, 1000);
    return () => {
      canceled = true;
      clearInterval(interval);
    };
  }, [apiConfig, roomInfo?.room_code, screen]);

  useEffect(() => {
    if (!roomInfo || (screen !== "room" && screen !== "roomGame" && screen !== "roomRole")) return;

    let canceled = false;
    const ping = async () => {
      try {
        const info = await api.roomHeartbeat(apiConfig, roomInfo.room_code);
        if (canceled) return;
        setRoomInfo(info);
        if (screen === "room" && (info.state === "started" || info.state === "paused")) {
          setScreen("roomGame");
        }
      } catch {
        // ignore transient heartbeat errors
      }
    };

    ping();
    const interval = setInterval(ping, 8000);
    return () => {
      canceled = true;
      clearInterval(interval);
    };
  }, [apiConfig, roomInfo?.room_code, screen]);

  useEffect(() => {
    if (!roomInfo || (screen !== "room" && screen !== "roomGame" && screen !== "roomRole")) return;

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
  }, [offlineRole?.image_url, offlineRole?.role]);

  useEffect(() => {
    setRoomImageOk(true);
  }, [roomRole?.image_url, roomRole?.role]);

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

  const clearSessionData = () => {
    leaveSentRef.current = false;
    setPendingOfflineCount(null);
    setOfflineSessionId(null);
    setOfflineTimerEnabled(false);
    setOfflineRole(null);
    setStarterPlayer(null);
    setOfflineTurn(null);
    setRoomInfo(null);
    setRoomRole(null);
    setRoomStarter(null);
    setRoomCodeInput("");
    setStatus(null);
    setTurnRemainingMs(null);
  };

  const resetAll = () => {
    setError(null);
    setFormat(null);
    setGameMode(null);
    setRoomPlayerLimit(MAX_PLAYERS);
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
    setRoomPlayerLimit(MAX_PLAYERS);
    setTimerEnabled(false);
    setTurnTimeSeconds(8);
    setScreen("playMode");
  };

  const pickStandardMode = () => {
    setError(null);
    setGameMode("standard");
    setRandomAllowed(DEFAULT_RANDOM_ALLOWED);
    setRoomPlayerLimit(MAX_PLAYERS);
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
    setRoomPlayerLimit(MAX_PLAYERS);
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

  const createRoomNow = async () => {
    if (format !== "online" || !gameMode) {
      setError("Сначала выбери формат и режим");
      return;
    }
    if (roomPlayerLimit < MIN_PLAYERS || roomPlayerLimit > MAX_PLAYERS) {
      setError("Выберите корректный лимит игроков");
      return;
    }
    if (gameMode === "random" && randomAllowed.length < 2) {
      setError("Выберите минимум два режима");
      return;
    }

    setError(null);

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
      setScreen("room");
    } catch (err) {
      setError(toUserError(err, "Не удалось создать комнату"));
    }
  };

  const handleJoinRoom = async () => {
    if (!roomCodeInput) return;
    if (format !== "online") {
      setError("Сначала выбери формат и режим");
      return;
    }

    setError(null);

    try {
      const info = await api.roomJoin(apiConfig, roomCodeInput.toUpperCase());
      setRoomInfo(info);
      setGameMode(info.play_mode);
      setRoomStarter(null);
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

  const handleRestartRoom = async () => {
    if (!roomInfo) return;
    setError(null);
    setStatus("Новая игра начинается…");

    try {
      const res = await api.roomRestart(apiConfig, roomInfo.room_code);
      setRoomStarter(`Игру начинает: ${res.starter_name}`);
      const info = await api.roomStatus(apiConfig, roomInfo.room_code);
      setRoomInfo(info);
      setStatus(null);
      setScreen("roomGame");
    } catch (err) {
      setStatus(null);
      setError(toUserError(err, "Не удалось перезапустить игру"));
    }
  };

  const handleGetRole = async () => {
    if (!roomInfo) return;
    setError(null);

    try {
      const res = await api.roomRole(apiConfig, roomInfo.room_code);
      setRoomRole({
        role: res.role,
        card: res.card,
        image_url: res.image_url,
        elixir_cost: res.elixir_cost,
      });
      setScreen("roomRole");
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

  const renderTimerSetup = () => (
    <div className="timer-options">
      <label className="toggle-row">
        <input
          type="checkbox"
          checked={timerEnabled}
          onChange={(e) => setTimerEnabled(e.target.checked)}
        />
        <span>Использовать таймер</span>
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
    <div className={`app ${isHome ? "bg-home" : "bg-game"}`}>
      <div className="screenOverlay" />
      <div className={`screenContent ${isHome ? "homeContent" : "gameContent"}`}>
        {isHome && (
          <>
            <header className="homeHeader">
              <div className="logo">Clash Royale Шпион</div>
            </header>

            {error && <div className="error">{error}</div>}
            {status && <div className="hint status">{status}</div>}

            <div className="homeActions">
              <div className="homeText">
                Выбери формат игры
                <span>Офлайн — один телефон. Онлайн — каждый игрок у себя.</span>
              </div>
              <button className="btn full" onClick={() => pickFormat("offline")}>
                Офлайн
              </button>
              <button className="btn secondary full" onClick={() => pickFormat("online")}>
                Онлайн
              </button>
            </div>
          </>
        )}

        {!isHome && (
          <>
            <header className="header">
              <div className="logo">Clash Royale Шпион</div>
            </header>

            {error && <div className="error">{error}</div>}
            {status && <div className="hint status">{status}</div>}

            {screen === "loading" && (
              <div className="card">
                <div className="title">Подготовка...</div>
              </div>
            )}

            {screen === "playMode" && (
              <div className="card bottom">
                <div className="title">Выбери режим</div>
                <div className="actions stack">
                  <button className="btn full" onClick={pickStandardMode}>
                    Стандартный
                  </button>
                  <button className="btn secondary full" onClick={pickRandomMode}>
                    Рандом
                  </button>
                </div>
                <button className="link" onClick={resetAll}>
                  Назад
                </button>
              </div>
            )}

            {screen === "randomInfo" && format === "offline" && (
              <div className="card center">
                <div className="title">Рандом режим</div>
                <p className="text">
                  Выберите режимы, которые хотите, чтобы могли выпасть. Бот случайно выберет один из
                  отмеченных режимов.
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

                <button className="link" onClick={() => setScreen("playMode")}>
                  Назад
                </button>
              </div>
            )}

            {screen === "onlineMenu" && format === "online" && gameMode && (
              <div className="card center">
                <div className="title">
                  Онлайн режим: {gameMode === "standard" ? "Стандартный" : "Рандом"}
                </div>
                <p className="text">Выберите, что хотите сделать.</p>
                <div className="actions stack">
                  <button className="btn full" onClick={() => setScreen("roomCreateSettings")}>
                    Создать комнату
                  </button>
                  <button className="btn secondary full" onClick={() => setScreen("joinRoom")}>
                    Подключиться
                  </button>
                </div>
                <button className="link" onClick={() => setScreen("playMode")}>
                  Назад
                </button>
              </div>
            )}

            {screen === "roomCreateSettings" && format === "online" && gameMode && (
              <div className="card center">
                <div className="title">Настройки комнаты</div>
                <p className="text">Выберите лимит игроков, затем дополнительные параметры.</p>

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
                </div>

                {gameMode === "random" && (
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
                )}

                {renderTimerSetup()}

                <div className="actions stack">
                  <button className="btn full" onClick={createRoomNow} disabled={gameMode === "random" && randomAllowed.length < 2}>
                    Создать
                  </button>
                </div>

                <button className="link" onClick={() => setScreen("onlineMenu")}>
                  Назад
                </button>
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

                <button className="link" onClick={() => setScreen("playMode")}>Назад</button>
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
                    <img className="spy-art" src="/assets/spy1.png" alt="Шпион" />
                  </div>
                )}
                {offlineRole.role === "card" && offlineRole.image_url && offlineImageOk && (
                  <div className="card-image-wrapper">
                    <img
                      className="card-image"
                      src={resolveImageUrl(offlineRole.image_url)}
                      alt="Карта"
                      onError={() => setOfflineImageOk(false)}
                    />
                    {typeof offlineRole.elixir_cost === "number" && (
                      <div className="elixir-badge" aria-label={`Эликсир ${offlineRole.elixir_cost}`}>
                        <img src="/assets/elik.png" alt="Эликсир" />
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
                <button className="link" onClick={backFromJoin}>
                  Назад
                </button>
              </div>
            )}

            {screen === "room" && roomInfo && (
              <div className="card center">
                <div className="title">
                  Код комнаты: <span className="room-code">{roomInfo.room_code}</span>
                </div>
                <p className="text">Хост: {roomInfo.host_name || roomInfo.owner_name}</p>
                <p className="text">Игроков: {roomInfo.player_count}</p>
                <p className="text">Лимит: {roomInfo.player_limit ?? MAX_PLAYERS}</p>
                <p className="text">Начинает: {starterDisplayName ?? "определится после старта"}</p>

                <div className="players">
                  {roomInfo.players.map((player) => (
                    <div key={player.user_id} className="player">
                      {player.display_name?.trim() ? player.display_name : "Не удалось получить имя из Telegram"}
                    </div>
                  ))}
                </div>

                {roomInfo.can_start ? (
                  <div className="actions">
                    <button className="btn" onClick={handleStartRoom}>
                      Начать игру
                    </button>
                  </div>
                ) : (
                  <div className="hint">Ожидаем минимум {MIN_PLAYERS} игроков</div>
                )}

                {roomInfo.status_message && <div className="hint">{roomInfo.status_message}</div>}
                <button className="link" onClick={resetAll}>
                  Новая игра
                </button>
              </div>
            )}

            {screen === "roomGame" && roomInfo && (
              <div className="card center room-game-card">
                <div className="title">
                  Код комнаты: <span className="room-code">{roomInfo.room_code}</span>
                </div>
                <p className="text">Хост: {roomInfo.host_name || roomInfo.owner_name}</p>

                <div className="players">
                  {roomInfo.players.map((player) => (
                    <div key={player.user_id} className="player">
                      {player.display_name?.trim() ? player.display_name : "Не удалось получить имя из Telegram"}
                    </div>
                  ))}
                </div>

                <div className="turn-board">
                  <div className="text">Начинает: {starterDisplayName ?? "—"}</div>
                  <div className="text">
                    Сейчас ход: {roomInfo.current_turn_name ?? `Игрок ${(roomInfo.current_turn_index ?? 0) + 1}`}
                  </div>

                  {roomInfo.timer_enabled && roomInfo.turn_state === "turn_loop_active" && roomInfo.state === "started" && renderTurnProgress()}

                  {roomInfo.state === "paused" && (
                    <div className="hint danger">
                      Игра на паузе. Таймер остановлен.
                    </div>
                  )}
                  {roomInfo.status_message && <div className="hint">{roomInfo.status_message}</div>}
                </div>

                <div className="actions stack">
                  <button className="btn" onClick={handleGetRole}>
                    Показать мою роль
                  </button>

                  {roomInfo.timer_enabled &&
                    roomInfo.turn_state === "ready_to_start" &&
                    roomInfo.state === "started" &&
                    roomInfo.you_are_owner && (
                      <button className="btn" onClick={handleStartRoomTurn}>
                        Начать игру
                      </button>
                    )}

                  {roomInfo.state === "paused" && roomInfo.you_are_owner && (
                    <button className="btn" onClick={handleResumeRoom}>
                      Продолжить игру
                    </button>
                  )}

                  {roomInfo.timer_enabled &&
                    roomInfo.turn_state === "turn_loop_active" &&
                    roomInfo.state === "started" &&
                    roomInfo.you_are_owner && (
                      <button className="btn secondary" onClick={handleFinishRoomTurn}>
                        Игра окончена
                      </button>
                    )}

                  {roomInfo.you_are_owner && (!roomInfo.timer_enabled || roomInfo.turn_state === "finished") && (
                    <button className="btn secondary" onClick={handleRestartRoom}>
                      Сыграть ещё
                    </button>
                  )}
                </div>

                <button className="leave-link" onClick={handleLeaveRoom}>
                  Выйти из комнаты
                </button>
              </div>
            )}

            {screen === "roomRole" && roomRole && (
              <div className="card center">
                <div className="title">Твоя роль</div>
                {roomRole.role === "spy" && (
                  <div className="card-image spy-frame">
                    <img className="spy-art" src="/assets/spy1.png" alt="Шпион" />
                  </div>
                )}
                {roomRole.role === "card" && roomRole.image_url && roomImageOk && (
                  <div className="card-image-wrapper">
                    <img
                      className="card-image"
                      src={resolveImageUrl(roomRole.image_url)}
                      alt="Карта"
                      onError={() => setRoomImageOk(false)}
                    />
                    {typeof roomRole.elixir_cost === "number" && (
                      <div className="elixir-badge" aria-label={`Эликсир ${roomRole.elixir_cost}`}>
                        <img src="/assets/elik.png" alt="Эликсир" />
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
                  <button className="btn" onClick={() => setScreen("roomGame")}>
                    Назад
                  </button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
