export type GameFormat = "offline" | "online";
export type GameMode = "standard" | "random";
export type TurnState = "waiting" | "ready_to_start" | "turn_loop_active" | "finished";

export type RoomInfo = {
  room_code: string;
  owner_user_id: number;
  owner_name: string;
  format_mode: GameFormat;
  play_mode: GameMode;
  players: { user_id: number; first_name?: string | null; last_name?: string | null; display_name: string }[];
  player_count: number;
  player_limit?: number;
  state: "waiting" | "started" | "finished";
  can_start: boolean;
  you_are_owner: boolean;
  starter_name?: string | null;
  timer_enabled?: boolean;
  turn_time_seconds?: number | null;
  turn_active?: boolean;
  turn_state?: TurnState;
  current_turn_index?: number;
  current_turn_name?: string | null;
  turn_started_at?: number | null;
  turns_completed?: boolean;
};
