# Go-Tone Marketplace — Implementation Brief

## Product Overview

Go-Tone is a Bluetooth LE smart resistance training device. The **Go-Tone Marketplace** is a storefront where customers can:

1. **Create an account** and subscribe
2. **Browse & purchase games** (interactive workout games)
3. **Play games** that control Go-Tone hardware via BLE in real-time

The core value proposition: the device's resistance (weight), exercise mode, and telemetry data form the input/output layer for gamified workouts.

---

## Architecture

```
┌─────────────────────────┐     ┌──────────────────────┐     ┌──────────────┐
│   Web App (Frontend)    │────▶│   API Server (Back)  │────▶│   Database   │
│  React/Vue + WebSocket  │     │  FastAPI/Node         │     │  PostgreSQL  │
└─────────────────────────┘     └──────────────────────┘     └──────────────┘
         │                                │
         ▼                                │
┌─────────────────┐                       │
│ Go-Tone Device │◀── BLE (local device) │
│  (BLE FFE1/FFE2)│                       │
└─────────────────┘                       │
```

**Key architectural decision:** The Go-Tone device connects via BLE from the user's device (phone/laptop). The BLE connection is local-to-device, **not** server-side. The backend manages accounts, subscriptions, game libraries, and score tracking; the frontend handles both the store and the game loop with BLE communication.

---

## System Components

### 1. User System

| Feature | Details |
|---------|---------|
| Registration | Email/password + OAuth (Google, Apple) |
| Authentication | JWT sessions, secure cookie storage |
| Profiles | Avatar, name, preferred exercise modes |
| Subscription tiers | Free (1 game), Basic ($9.99/mo, 5 games), Pro ($19.99/mo, all games + live leaderboards) |

### 2. Storefront

| Feature | Details |
|---------|---------|
| Game catalog | Card grid with images, descriptions, ratings |
| Game categories | Strength, cardio, flexibility, full body |
| Game detail page | Screenshots, description, difficulty, "play" button |
| Purchasing | In-app purchase flow, subscription management |
| Wishlist | Save games for later |
| Reviews & ratings | Star ratings + written reviews |

### 3. Game Library

| Feature | Details |
|---------|---------|
| Game manifest | JSON manifest describing each game (metadata, BLE commands, scoring rules) |
| Game runtime | Web-based game engine that speaks Go-Tone BLE protocol |
| Difficulty levels | Each game has 3 difficulty tiers that map to weight ranges |
| Leaderboards | Per-game global + friend leaderboards (Pro tier) |

### 4. Game Runtime (BLE Client)

This is the critical layer — it translates game inputs to Go-Tone device commands:

**BLE Protocol Summary (from Go-Tone docs):**

```
Device UUIDs:
  Write (commands)  : 0000FFE1-0000-1000-8000-00805F9B34FB
  Notify (replies)  : 0000FFE2-0000-1000-8000-00805F9B34FB
  Parent service    : 54430001-0354-432d-4a53-2d5031fbffff

Packet format:
  TX: 5A 21 | Hi | Lo | Len | Data | CRC-16/XMODEM (big-endian)
  RX: 5A B1 | Hi | Lo | Len | Data | CRC-16/XMODEM (big-endian)

Core operations:
  Set weight (W lbs):  CMD 02 10, data = W as uint16 BE
  Get weight:          Read telemetry 5A B1 01 10, data[17:19] = uint16 BE lbs
  Start workout:       20 10 → 16 10 → 17 10 (start, clear reps, clear distance)
  Pause workout:       19 10
  Set mode (1-6):      CMD 06 10, data = mode byte
  Eccentric ratio:     CMD 07 10, data = ratio byte

Telemetry (01 10 NOTIFY):
  mid = int16 LE at offsets [6..7]  — primary motion signal
  weight = uint16 BE at data offset 17
```

**Game-to-device mapping:**

| Game element | BLE command |
|-------------|-------------|
| Player pulls rope → resistance changes | `02 10` (set weight) |
| Monster attacks → device pulses | Exercise mode switch |
| Score calculation | `mid` velocity from telemetry |
| Rep counting | Telemetry counter (pull = abs(mid) > 800) |
| Distance tracking | Integrate abs(mid) × dt × 0.000179 |
| "cal" (effort score) | 2.0 × weightLbs × meters |

### 5. Game Manifest Format

```json
{
  "id": "dragon-pull",
  "title": "Dragon Pull",
  "description": "Pull rope to feed and strengthen your dragon...",
  "category": "strength",
  "difficulty": [1, 3, 5],
  "min_weight_lbs": 8,
  "max_weight_lbs": 50,
  "default_mode": 1,
  "ble_commands": {
    "pull_to_resist": { "high": 2, "low": 16 },
    "start_workout": 32,
    "pause_workout": 25
  },
  "scoring": {
    "base_cal_k": 2.0,
    "distance_scale": 0.000179,
    "speed_scale": 0.000557,
    "pull_threshold": 800,
    "rest_threshold": 300
  }
}
```

### 6. Backend API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/auth/register` | POST | Create account |
| `/api/auth/login` | POST | Login, return JWT |
| `/api/auth/refresh` | POST | Refresh token |
| `/api/games` | GET | List all games (public) |
| `/api/games/:id` | GET | Game detail |
| `/api/games/:id/reviews` | GET/POST | Reviews for game |
| `/api/library` | GET | User's game library |
| `/api/library/:gameId` | POST | Add to library |
| `/api/library/:gameId/remove` | DELETE | Remove from library |
| `/api/user/profile` | GET/PUT | User profile management |
| `/api/subscription/status` | GET | Current subscription tier |
| `/api/subscription/checkout` | POST | Init checkout (Stripe) |
| `/api/submissions` | POST | Submit game score |
| `/api/leaderboard/:gameId` | GET | Leaderboard for game |
| `/api/notifications` | GET | User notifications |

### 7. Web Tester Integration

The repo already contains a working **web tester** (`tools/ble_test/`) that serves as partial reference implementation for the game runtime:

- `server.py` — aiohttp WebSocket backend with BLE abstraction
- `session.py` — Proven BLE session class (Bleak-based)
- `sim_session.py` — In-memory simulation (no Bluetooth needed for dev)
- `static/index.html` — Full UI with connection, weight, workout, mode panels
- `protocol.py` — CRC-16/XMODEM framing, packet building/parsing

**Reuse strategy:** Fork `web_tester/` into a reusable `gotone-ble-client` package that the game runtime imports.

---

## Tech Stack Recommendations

| Layer | Recommendation | Notes |
|-------|---------------|-------|
| Frontend | React + TypeScript + Vite | BLE API available in modern browsers (Web Bluetooth) |
| BLE layer | Web Bluetooth API + gotone-ble-client | Or Electron for desktop |
| Backend | FastAPI (Python) or Node/Express | FastAPI for protocol consistency with team's ble_test code |
| Database | PostgreSQL + Prisma | Users, games, subscriptions, scores |
| Auth | JWT + HTTP-only cookies | Or Auth.js / Clerk |
| Storage | AWS S3 or Cloudflare R2 | Game assets, user uploads |
| Payments | Stripe | Subscriptions + one-time game purchases |
| Notifications | Web Push API | Reminders, leaderboard alerts |
| Testing | Playwright (E2E), Jest (unit) | SimGoToneSession for BLE-heavy unit tests |

---

## Game Types

### Category ideas based on Go-Tone capabilities:

1. **Resistance RPG** — Pull rope against monster weight; weight scales with difficulty
2. **Rhythm Pull** — Sync your pulls to music using `mid` velocity timing
3. **Chain Reaction** — Mode 5 (Iron Chain) game where resistance increases per rep
4. **Rowing Race** — Mode 4 (Rowing) with real-time speed competition
5. **Concentric Trainer** — Mode 3 focusing on controlled release
6. **Power Hitter** — Quick max-effort pulls measured by telemetry velocity
7. **Endurance Mode** — Mode 6 (Power Saving) for long low-intensity sessions

---

## Data Models

```
User {
  id: UUID
  email: string
  password_hash: string
  name: string
  avatar_url: string
  subscription_tier: enum[free, basic, pro]
  created_at: datetime
}

Game {
  id: UUID
  slug: string
  title: string
  description: text
  thumbnail_url: string
  category: enum[strength, cardio, flexibility, full_body]
  difficulty: [int, int, int]  // 3 tiers
  min_weight_lbs: int
  max_weight_lbs: int
  default_mode: int (1-6)
  manifest: json  // scoring rules, BLE commands, game logic
  rating_avg: float
  rating_count: int
  is_premium: bool
  price: float
}

Subscription {
  id: UUID
  user_id: UUID
  tier: enum[free, basic, pro]
  stripe_sub_id: string
  status: enum[active, past_due, canceled, trialing]
  current_period_end: datetime
}

GamePlay {
  id: UUID
  user_id: UUID
  game_id: UUID
  weight_lbs: int
  score: float
  duration_seconds: float
  reps: int
  meters: float
  cal: float
  created_at: datetime
}

Review {
  id: UUID
  user_id: UUID
  game_id: UUID
  rating: int (1-5)
  comment: text
  created_at: datetime
}
```

---

## Implementation Phases

### Phase 1: MVP Store
- User auth (register/login/JWT)
- Game catalog with 5 placeholder games
- Subscription billing (Stripe test mode)
- Basic game detail pages

### Phase 2: Game Runtime
- BLE client library (from ble_test code)
- 3 playable games with game manifests
- Score submission to backend
- Leaderboards per game

### Phase 3: Full Marketplace
- Review/rating system
- Wishlist + notifications
- Social features (share scores)
- More games (8+)
- Pro tier features (live leaderboards, cross-device sync)

---

## Key Constraints & Gotchas

1. **BLE is local-only** — The device connects from the browser/device, not the server. Web Bluetooth API has limited support; consider Electron wrapper for desktop.
2. **Weight via telemetry, not commands** — `14 10` get-weight does NOT work on current firmware. Always read weight from telemetry `01 10` data offset 17.
3. **Only one BLE central** — Disconnect nRF Connect / TT BOT before connecting.
4. **RSSI threshold** — Stay within ~10m; Windows needs RSSI better than -80.
5. **"cal" is effort points not food calories** — ~73 cal in 30 sec at 10 lb / 4 m is physically impossible as food energy. Label as "effort" in UI.
6. **Write With Response preferred on Windows** — Write Without Response works once link is solid but With Response is more reliable.
7. **CRC-16/XMODEM** — Always use the library, never hand-edit checksums.
