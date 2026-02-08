export type GameFormat = "offline" | "online";
export type GameMode = "standard" | "random";

export type RoomInfo = {
  room_code: string;
  owner_user_id: number;
  owner_name: string;
  format_mode: GameFormat;
  play_mode: GameMode;
  players: { user_id: number; first_name?: string | null; last_name?: string | null; display_name: string }[];
  player_count: number;
  state: "waiting" | "started" | "finished";
  can_start: boolean;
  you_are_owner: boolean;
  starter_name?: string | null;
  discussion_time_seconds?: number | null;
  discussion_started_at?: number | null;
};
