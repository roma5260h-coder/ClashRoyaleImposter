import type { GameFormat, GameMode, RoomInfo } from "./types";

type ApiConfig = {
  baseUrl: string;
  initData: string;
};

async function post<T>(config: ApiConfig, path: string, body: Record<string, unknown>) {
  const res = await fetch(`${config.baseUrl}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ initData: config.initData, ...body }),
  });

  if (!res.ok) {
    let message = "Ошибка запроса";
    const text = await res.text();
    if (text) {
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
    discussionTimeSeconds: number,
    randomAllowed?: string[]
  ) =>
    post<{ session_id: string; current_player_number: number; player_count: number; discussion_time_seconds: number }>(
      config,
      "/api/offline/start",
      {
        game_mode: gameMode,
        player_count: playerCount,
        discussion_time_seconds: discussionTimeSeconds,
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
    post<{ session_id: string; current_player_number: number; player_count: number }>(
      config,
      "/api/offline/restart",
      { session_id: sessionId }
    ),

  roomCreate: (
    config: ApiConfig,
    formatMode: GameFormat,
    gameMode: GameMode,
    discussionTimeSeconds: number,
    randomAllowed?: string[]
  ) =>
    post<RoomInfo>(config, "/api/room/create", {
      format_mode: formatMode,
      game_mode: gameMode,
      discussion_time_seconds: discussionTimeSeconds,
      ...(randomAllowed ? { random_allowed_modes: randomAllowed } : {}),
    }),

  roomJoin: (config: ApiConfig, roomCode: string, formatMode: GameFormat, gameMode: GameMode) =>
    post<RoomInfo>(config, "/api/room/join", {
      room_code: roomCode,
      format_mode: formatMode,
      game_mode: gameMode,
    }),

  roomStatus: (config: ApiConfig, roomCode: string) =>
    post<RoomInfo>(config, "/api/room/status", { room_code: roomCode }),

  roomStart: (config: ApiConfig, roomCode: string) =>
    post<{ started: boolean; starter_user_id: number; starter_name: string }>(
      config,
      "/api/room/start",
      { room_code: roomCode }
    ),
  roomRestart: (config: ApiConfig, roomCode: string) =>
    post<{ started: boolean; starter_user_id: number; starter_name: string }>(
      config,
      "/api/room/restart",
      { room_code: roomCode }
    ),

  roomRole: (config: ApiConfig, roomCode: string) =>
    post<{ role: "spy" | "card"; card?: string; image_url?: string; elixir_cost?: number | null }>(
      config,
      "/api/room/role",
      { room_code: roomCode }
    ),
};

export type { ApiConfig };
