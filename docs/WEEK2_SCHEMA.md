# Week 2: Schema diagram

All data is fictional. Every profile row is owned by exactly one user through `user_id`
(FK to `users.id`, `ON DELETE CASCADE`). The API derives `user_id` from the JWT, never from the request body.

```mermaid
erDiagram
    users ||--o| demographics : "has 0..1"
    users ||--o| wellness_preferences : "has 0..1"
    users ||--o{ emergency_contacts : "has 0..5"
    users ||--o{ admin_sessions : "admin only"
    users |o--o{ audit_events : "acts in"

    users {
        int id PK
        string email UK "indexed"
        string full_name
        string password_hash "bcrypt, never returned"
        bool is_admin
        datetime created_at
    }
    demographics {
        int id PK
        int user_id FK,UK "1:1"
        date date_of_birth
        string gender
        string city "indexed for admin filter"
        string country
        datetime updated_at
    }
    wellness_preferences {
        int id PK
        int user_id FK,UK "1:1"
        string activity_level "low|moderate|high"
        string diet_notes
        bool reminder_opt_in
        datetime updated_at
    }
    emergency_contacts {
        int id PK
        int user_id FK "indexed, max 5 per user"
        string name
        string phone
        string relationship
        datetime created_at
    }
    admin_sessions {
        string id PK "opaque session id"
        int user_id FK
        datetime created_at
        datetime expires_at
        bool revoked
    }
    audit_events {
        int id PK
        int actor_user_id FK "SET NULL on user delete"
        string action "profile.create|profile.update|profile.delete|admin.profiles.list"
        string resource_type
        string resource_id
        json metadata_json "changed field names or filter keys only"
        datetime created_at "index (actor_user_id, created_at)"
    }
```

Design choices:
- Demographic and wellness are 1:1 (unique `user_id`) with `PUT` upsert: one current version per user.
- Emergency contacts are 1:N, capped at 5 per user in the API (409 beyond that), enforced atomically with a SQLite `BEGIN IMMEDIATE` reservation. Phones are stored canonical (`+` optional, then 7 to 15 digits) and unique per user.
- Audit metadata stores which fields changed or which filters were used, never values,
  passwords, or tokens, so the audit log does not become a second copy of profile data.
