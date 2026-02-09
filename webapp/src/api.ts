import type { GameFormat, GameMode, RoomInfo, TurnState } from "./types";

type ApiConfig = {
  baseUrl: string;
  initData: string;
};

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

async function post<T>(config: ApiConfig, path: string, body: Record<string, unknown>) {
  const res = await fetch(`${config.baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initData: config.initData, ...body }),
  });

  if (!res.ok) {
    let message = "Произошла ошибка, попробуйте ещё раз";
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
  return (await res.json()) as T;
}

export const api = {
  auth: (config: ApiConfig) => post<{ user_id: number; username?: string; full_name?: string }>(config, "/api/auth", {}),

  offlineStart: (
    config: ApiConfig,
    gameMode: GameMode,
    playerCount: number,
    timerEnabled: boolean,
    turnTimeSeconds: number | null,
    randomAllowed?: string[]
  ) =>
    post<{ session_id: string; current_player_number: number; player_count: number; timer_enabled: boolean; turn_time_seconds?: number | null }>(
      config,
      "/api/offline/start",
      {
        game_mode: gameMode,
        player_count: playerCount,
        timer_enabled: timerEnabled,
        ...(timerEnabled && turnTimeSeconds ? { turn_time_seconds: turnTimeSeconds } : {}),
        ...(randomAllowed ? { random_allowed_modes: randomAllowed } : {}),
      }
    ),

  offlineReveal: (config: ApiConfig, sessionId: string) =>
    post<{ player_number: number; role: "spy" | "card"; card?: string; image_url?: string; elixir_cost?: number | null }>(
      config,
      "/api/offline/reveal",
      { session_id: sessionId }
    ),

  offlineClose: (config: ApiConfig, sessionId: string) =>
    post<{ finished: boolean; current_player_number?: number; starter_player_number?: number }>(
      config,
      "/api/offline/close",
      { session_id: sessionId }
    ),
  offlineRestart: (config: ApiConfig, sessionId: string) =>
    post<{ session_id: string; current_player_number: number; player_count: number; timer_enabled: boolean; turn_time_seconds?: number | null }>(
      config,
      "/api/offline/restart",
      { session_id: sessionId }
    ),

  offlineTurnStatus: (config: ApiConfig, sessionId: string) =>
    post<OfflineTurnStatus>(config, "/api/offline/turn/status", { session_id: sessionId }),

  offlineTurnStart: (config: ApiConfig, sessionId: string) =>
    post<OfflineTurnStatus>(config, "/api/offline/turn/start", { session_id: sessionId }),

  offlineTurnFinish: (config: ApiConfig, sessionId: string) =>
    post<OfflineTurnStatus>(config, "/api/offline/turn/finish", { session_id: sessionId }),

  roomCreate: (
    config: ApiConfig,
    formatMode: GameFormat,
    gameMode: GameMode,
    playerLimit: number,
    timerEnabled: boolean,
    turnTimeSeconds: number | null,
    randomAllowed?: string[]
  ) =>
    post<RoomInfo>(config, "/api/room/create", {
      format_mode: formatMode,
      game_mode: gameMode,
      player_limit: playerLimit,
      timer_enabled: timerEnabled,
      ...(timerEnabled && turnTimeSeconds ? { turn_time_seconds: turnTimeSeconds } : {}),
      ...(randomAllowed ? { random_allowed_modes: randomAllowed } : {}),
    }),

  roomJoin: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/join", {
      room_code: roomCode,
    }),

  roomStatus: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/status", { room_code: roomCode }),

  roomStart: (config: ApiConfig, roomCode: string) =>
    post<{ started: boolean; starter_user_id: string; starter_name: string }>(
      config,
      "/api/room/start",
      { room_code: roomCode }
    ),
  roomRestart: (config: ApiConfig, roomCode: string) =>
    post<{ started: boolean; starter_user_id: string; starter_name: string }>(
      config,
      "/api/room/restart",
      { room_code: roomCode }
    ),

  roomToLobby: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/lobby", { room_code: roomCode }),

  roomTurnStart: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/turn/start", { room_code: roomCode }),

  roomTurnFinish: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/turn/finish", { room_code: roomCode }),

  roomResume: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/resume", { room_code: roomCode }),

  roomHeartbeat: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/heartbeat", { room_code: roomCode }),

  roomLeave: (config: ApiConfig, roomCode: string) =>
    post<{ left: boolean; room_closed: boolean }>(config, "/api/room/leave", { room_code: roomCode }),

  roomBotsAdd: (config: ApiConfig, roomCode: string, count: number) =>
    post<RoomInfo>(config, "/api/room/bots/add", { room_code: roomCode, count }),

  roomBotsFill: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/bots/fill", { room_code: roomCode }),

  roomBotsClear: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/bots/clear", { room_code: roomCode }),

  roomRole: (config: ApiConfig, roomCode: string) =>
    post<{ role: "spy" | "card"; card?: string; image_url?: string; elixir_cost?: number | null }>(
      config,
      "/api/room/role",
      { room_code: roomCode }
    ),
};

export type { ApiConfig };
