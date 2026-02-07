import React, { useEffect, useMemo, useState } from "react";
import { api, type ApiConfig } from "./api";
import type { GameFormat, GameMode, RoomInfo } from "./types";

const tg = (window as any).Telegram?.WebApp;

type Screen =
  | "loading"
  | "format"
  | "playMode"
  | "randomInfo"
  | "offlinePlayers"
  | "offlinePlayer"
  | "offlineRole"
  | "offlineNext"
  | "offlineFinished"
  | "onlineMenu"
  | "joinRoom"
  | "room"
  | "roomRole";

const RANDOM_SCENARIOS = [
  { id: "all_spies", label: "Все шпионы" },
  { id: "same_card", label: "У всех одна карта" },
  { id: "different_cards", label: "У всех разные карты" },
  { id: "multi_spy", label: "Несколько шпионов" },
];

export default function App() {
  const [screen, setScreen] = useState<Screen>("loading");
  const [error, setError] = useState<string | null>(null);
  const [format, setFormat] = useState<GameFormat | null>(null);
  const [gameMode, setGameMode] = useState<GameMode | null>(null);
  const [randomAllowed, setRandomAllowed] = useState<string[]>(() => RANDOM_SCENARIOS.map((s) => s.id));
  const [randomFlow, setRandomFlow] = useState<"offline" | "onlineCreate" | null>(null);

  const [offlineSessionId, setOfflineSessionId] = useState<string | null>(null);
  const [currentPlayer, setCurrentPlayer] = useState<number>(1);
  const [offlineRole, setOfflineRole] = useState<{ role: string; card?: string; image_url?: string; elixir_cost?: number | null } | null>(null);
  const [offlineImageOk, setOfflineImageOk] = useState<boolean>(true);
  const [starterPlayer, setStarterPlayer] = useState<number | null>(null);
  const [status, setStatus] = useState<string | null>(null);

  const [roomInfo, setRoomInfo] = useState<RoomInfo | null>(null);
  const [roomCodeInput, setRoomCodeInput] = useState<string>("");
  const [roomRole, setRoomRole] = useState<{ role: string; card?: string; image_url?: string; elixir_cost?: number | null } | null>(null);
  const [roomImageOk, setRoomImageOk] = useState<boolean>(true);
  const [roomStarter, setRoomStarter] = useState<string | null>(null);

  const [initData, setInitData] = useState<string>(() => tg?.initData ?? "");
  const apiBase = import.meta.env.VITE_API_BASE ?? "";
  const resolveImageUrl = (url: string) => {
    if (/^https?:\/\//i.test(url)) return url;
    if (!apiBase) return url;
    const trimmed = apiBase.replace(/\/$/, "");
    return `${trimmed}${url.startsWith("/") ? "" : "/"}${url}`;
  };

  const apiConfig: ApiConfig = useMemo(
    () => ({ baseUrl: apiBase, initData }),
    [apiBase, initData]
  );

  useEffect(() => {
    tg?.ready?.();
    tg?.expand?.();

    if (initData) return;

    let attempts = 0;
    const timer = setInterval(() => {
      const freshInitData = tg?.initData ?? "";
      if (freshInitData) {
        setError(null);
        setInitData(freshInitData);
        clearInterval(timer);
        return;
      }
      attempts += 1;
      if (attempts >= 5) {
        clearInterval(timer);
        setError("Не удалось получить имя из Telegram. Открой мини‑приложение из Telegram.");
        setScreen("format");
      }
    }, 200);

    return () => clearInterval(timer);
  }, [initData]);

  useEffect(() => {
    if (!initData) return;
    api
      .auth(apiConfig)
      .then(() => setScreen("format"))
      .catch((err) => {
        setError(err.message || "Не удалось подтвердить Telegram");
        setScreen("format");
      });
  }, [apiConfig, initData]);

  useEffect(() => {
    if (screen === "randomInfo") {
      setRandomAllowed(RANDOM_SCENARIOS.map((s) => s.id));
    }
  }, [screen]);

  useEffect(() => {
    if (screen !== "room" || !roomInfo) return;

    const interval = setInterval(() => {
      api
        .roomStatus(apiConfig, roomInfo.room_code)
        .then((info) => {
          setRoomInfo(info);
          if (info.state === "started") {
            const starter = info.starter_name
              ? `Игру начинает: ${info.starter_name}`
              : "Игра началась";
            setRoomStarter((prev) => prev ?? starter);
          }
        })
        .catch(() => null);
    }, 3000);

    return () => clearInterval(interval);
  }, [screen, roomInfo, apiConfig]);

  useEffect(() => {
    setOfflineImageOk(true);
  }, [offlineRole?.image_url, offlineRole?.role]);

  useEffect(() => {
    setRoomImageOk(true);
  }, [roomRole?.image_url, roomRole?.role]);

  const resetAll = () => {
    setFormat(null);
    setGameMode(null);
    setRandomFlow(null);
    setOfflineSessionId(null);
    setOfflineRole(null);
    setStarterPlayer(null);
    setRoomInfo(null);
    setRoomRole(null);
    setRoomStarter(null);
    setRoomCodeInput("");
    setStatus(null);
    setScreen("format");
  };

  const proceedAfterMode = () => {
    if (format === "offline") {
      setScreen("offlinePlayers");
    } else {
      setScreen("onlineMenu");
    }
  };

  const handleStartOffline = async (count: number) => {
    if (!gameMode) return;
    setError(null);
    try {
      const res = await api.offlineStart(
        apiConfig,
        gameMode,
        count,
        gameMode === "random" ? randomAllowed : undefined
      );
      setOfflineSessionId(res.session_id);
      setCurrentPlayer(res.current_player_number);
      setScreen("offlinePlayer");
    } catch (err: any) {
      setError(err.message || "Не удалось начать игру");
    }
  };

  const handleReveal = async () => {
    if (!offlineSessionId) return;
    setError(null);
    try {
      const res = await api.offlineReveal(apiConfig, offlineSessionId);
      console.debug("offline role payload", res);
      setOfflineRole({ role: res.role, card: res.card, image_url: res.image_url, elixir_cost: res.elixir_cost });
      setScreen("offlineRole");
    } catch (err: any) {
      setError(err.message || "Не удалось показать роль");
    }
  };

  const handleClose = async () => {
    if (!offlineSessionId) return;
    setError(null);
    try {
      const res = await api.offlineClose(apiConfig, offlineSessionId);
      if (res.finished) {
        setStarterPlayer(res.starter_player_number ?? null);
        setScreen("offlineFinished");
      } else if (res.current_player_number) {
        setCurrentPlayer(res.current_player_number);
        setScreen("offlineNext");
      }
    } catch (err: any) {
      setError(err.message || "Не удалось продолжить");
    }
  };

  const createRoomNow = async () => {
    if (!gameMode || format !== "online") {
      setError("Сначала выбери формат и режим");
      return;
    }
    setError(null);
    try {
      const info = await api.roomCreate(
        apiConfig,
        format,
        gameMode,
        gameMode === "random" ? randomAllowed : undefined
      );
      setRoomInfo(info);
      setFormat(info.format_mode);
      setGameMode(info.play_mode);
      setScreen("room");
    } catch (err: any) {
      setError(err.message || "Не удалось создать комнату");
    }
  };

  const handleCreateRoom = async () => {
    if (gameMode === "random") {
      setRandomFlow("onlineCreate");
      setScreen("randomInfo");
      return;
    }
    await createRoomNow();
  };

  const handleJoinRoom = async () => {
    if (!roomCodeInput) return;
    if (!gameMode || format !== "online") {
      setError("Сначала выбери формат и режим");
      return;
    }
    setError(null);
    try {
      const info = await api.roomJoin(apiConfig, roomCodeInput.toUpperCase(), format, gameMode);
      setRoomInfo(info);
      setFormat(info.format_mode);
      setGameMode(info.play_mode);
      setScreen("room");
    } catch (err: any) {
      setError(err.message || "Не удалось подключиться");
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
    } catch (err: any) {
      setError(err.message || "Не удалось начать игру");
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
    } catch (err: any) {
      setStatus(null);
      setError(err.message || "Не удалось перезапустить игру");
    }
  };

  const handleRestartOffline = async () => {
    if (!offlineSessionId) return;
    setError(null);
    setStatus("Новая игра начинается…");
    try {
      const res = await api.offlineRestart(apiConfig, offlineSessionId);
      setOfflineSessionId(res.session_id);
      setCurrentPlayer(res.current_player_number);
      setOfflineRole(null);
      setStarterPlayer(null);
      setStatus(null);
      setScreen("offlinePlayer");
    } catch (err: any) {
      setStatus(null);
      setError(err.message || "Не удалось перезапустить игру");
    }
  };

  const handleGetRole = async () => {
    if (!roomInfo) return;
    setError(null);
    try {
      const res = await api.roomRole(apiConfig, roomInfo.room_code);
      console.debug("room role payload", res);
      setRoomRole({ role: res.role, card: res.card, image_url: res.image_url, elixir_cost: res.elixir_cost });
      setScreen("roomRole");
    } catch (err: any) {
      setError(err.message || "Не удалось получить роль");
    }
  };

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
              <button
                className="btn full"
                onClick={() => {
                  setFormat("offline");
                  setScreen("playMode");
                }}
              >
                Офлайн
              </button>
              <button
                className="btn secondary full"
                onClick={() => {
                  setFormat("online");
                  setScreen("playMode");
                }}
              >
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
            <button
              className="btn full"
              onClick={() => {
                setGameMode("standard");
                proceedAfterMode();
              }}
            >
              Стандартный
            </button>
            <button
              className="btn secondary full"
              onClick={() => {
                setGameMode("random");
                if (format === "online") {
                  setScreen("onlineMenu");
                } else {
                  setRandomFlow("offline");
                  setScreen("randomInfo");
                }
              }}
            >
              Рандом
            </button>
          </div>
          <button className="link" onClick={resetAll}>Назад</button>
        </div>
      )}

      {screen === "randomInfo" && (
        <div className="card center">
          <div className="title">Рандом режим</div>
          <p className="text">
            Выберите режимы, которые хотите, чтобы могли выпасть. Бот случайно выберет один из отмеченных режимов.
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
          {randomAllowed.length < 2 && (
            <div className="hint danger">Выберите минимум два режима</div>
          )}
          <div className="actions">
            <button
              className="btn full"
              onClick={() => {
                if (randomFlow === "onlineCreate") {
                  setRandomFlow(null);
                  createRoomNow();
                  return;
                }
                setRandomFlow("offline");
                proceedAfterMode();
              }}
              disabled={randomAllowed.length < 2}
            >
              Продолжить
            </button>
          </div>
          <button className="link" onClick={() => { setRandomFlow(null); setScreen("playMode"); }}>Назад</button>
        </div>
      )}

      {screen === "offlinePlayers" && (
        <div className="card center">
          <div className="title">Сколько игроков?</div>
          <div className="grid">
            {Array.from({ length: 10 }, (_, i) => i + 3).map((count) => (
              <button key={count} className="btn small" onClick={() => handleStartOffline(count)}>
                {count}
              </button>
            ))}
          </div>
          <button className="link" onClick={() => setScreen("playMode")}>Назад</button>
        </div>
      )}

      {screen === "offlinePlayer" && (
        <div className="card center">
          <div className="title">Игрок {currentPlayer}</div>
          <p className="text">Нажми кнопку, чтобы увидеть свою карту.</p>
          <div className="actions">
            <button className="btn" onClick={handleReveal}>Показать карту</button>
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
          <div className="role">
            {offlineRole.role === "spy" ? "🕵️ Ты шпион" : `🗺️ Карта: ${offlineRole.card}`}
          </div>
          <div className="actions">
            <button className="btn" onClick={handleClose}>Закрыть</button>
          </div>
        </div>
      )}

      {screen === "offlineNext" && (
        <div className="card center">
          <div className="title">Передайте телефон следующему игроку</div>
          <p className="text">Когда будете готовы, продолжайте.</p>
          <div className="actions">
            <button className="btn" onClick={() => setScreen("offlinePlayer")}>Продолжить</button>
          </div>
        </div>
      )}

      {screen === "offlineFinished" && (
        <div className="card center">
          <div className="title">Роли розданы</div>
          <p className="text">Игру начинает: Игрок {starterPlayer ?? "?"}</p>
          <div className="actions">
            <button className="btn" onClick={handleRestartOffline}>Сыграть ещё</button>
            <button className="btn" onClick={resetAll}>Новая игра</button>
          </div>
        </div>
      )}

      {screen === "onlineMenu" && (
        <div className="card bottom">
          <div className="title">Онлайн игра</div>
          <p className="text">Создай комнату или подключись по коду.</p>
          <div className="actions stack">
            <button className="btn full" onClick={handleCreateRoom}>Создать комнату</button>
            <button className="btn secondary full" onClick={() => setScreen("joinRoom")}>Подключиться</button>
          </div>
          <button className="link" onClick={() => setScreen("playMode")}>Назад</button>
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
            <button className="btn full" onClick={handleJoinRoom}>Войти</button>
          </div>
          <button className="link" onClick={() => setScreen("onlineMenu")}>Назад</button>
        </div>
      )}

      {screen === "room" && roomInfo && (
        <div className="card center">
          <div className="title">
            Код комнаты: <span className="room-code">{roomInfo.room_code}</span>
          </div>
          <p className="text">Игроков: {roomInfo.player_count}</p>
          <div className="players">
            {roomInfo.players.map((p) => (
              <div key={p.user_id} className="player">
                {p.display_name?.trim() ? p.display_name : "Не удалось получить имя из Telegram"}
              </div>
            ))}
          </div>

          {roomInfo.state === "waiting" && (
            <div className="actions">
              {roomInfo.can_start && (
                <button className="btn" onClick={handleStartRoom}>Начать игру</button>
              )}
              {!roomInfo.can_start && (
                <div className="hint">Ожидаем минимум {MIN_PLAYERS} игроков</div>
              )}
            </div>
          )}

          {roomInfo.state === "started" && (
            <div className="actions">
              <button className="btn" onClick={handleGetRole}>Показать мою роль</button>
              {roomInfo.you_are_owner && (
                <button className="btn secondary" onClick={handleRestartRoom}>Сыграть ещё</button>
              )}
            </div>
          )}

          {roomStarter && <div className="hint">{roomStarter}</div>}
          <button className="link" onClick={resetAll}>Новая игра</button>
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
          <div className="role">
            {roomRole.role === "spy" ? "🕵️ Ты шпион" : `🗺️ Карта: ${roomRole.card}`}
          </div>
          <div className="actions">
            <button className="btn" onClick={() => setScreen("room")}>Назад</button>
          </div>
        </div>
      )}
          </>
        )}
      </div>
    </div>
  );
}

const MIN_PLAYERS = 3;
