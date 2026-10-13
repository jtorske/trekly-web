-- CampAlert (Parks Canada) schema.
--
-- This file is mounted into the MySQL container's
-- /docker-entrypoint-initdb.d/ so it runs automatically against a fresh
-- volume (see docker-compose.yml). It's also the source of truth for
-- migrations: it's written idempotently (CREATE TABLE IF NOT EXISTS) so it
-- can be re-run safely, and 002+/*.sql files can be added later for schema
-- changes once this is running in an environment with real data in it.

SET NAMES utf8mb4;

-- One row per Parks Canada resourceLocationId (a park/campground area, e.g.
-- Banff National Park front-country camping).
--
-- pc_resource_location_id is signed: confirmed real IDs include negative
-- values (e.g. -2147483531 for the "Internet" utility entry), so an
-- UNSIGNED column would silently clamp those to 0 under non-strict SQL
-- modes instead of erroring.
CREATE TABLE IF NOT EXISTS campgrounds (
  id                        INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  pc_resource_location_id   INT NOT NULL,
  name                      VARCHAR(255) NOT NULL,
  region                    VARCHAR(255) NULL,
  last_synced_at            DATETIME NULL,
  created_at                DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_campgrounds_resource_location_id (pc_resource_location_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- One row per bookable site under a campground (resourceModel = 2 only —
-- catalogSync filters out 3/0 before writing here). pc_resource_id is
-- stored as a string since it's used verbatim as an object key in the
-- availability/map response (resourceAvailabilities[resourceId]).
--
-- resource_category_id / is_backcountry: backcountry-vs-frontcountry is a
-- per-site distinction, not a per-campground one — a single park
-- (campgrounds row) can mix backcountry zones and frontcountry drive-in
-- loops under one resourceLocationId, so the classification lives here
-- rather than on campgrounds. resource_category_id stores the raw field
-- from the API verbatim (signed, for the same reason as
-- pc_resource_location_id above; nullable — may be absent) so scope can
-- widen to frontcountry later without a schema change, purely by changing
-- the catalogSync filter. is_backcountry is nullable on purpose: NULL means
-- "catalogSync couldn't confidently classify this one" (logged, not
-- guessed) rather than silently defaulting it either way. As of the
-- location-name-based backcountry filter, every synced site is classified
-- confidently (true) since scope is backcountry-only for now — NULL is
-- reserved for once frontcountry sites start getting synced too.
CREATE TABLE IF NOT EXISTS sites (
  id                    INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  campground_id         INT UNSIGNED NOT NULL,
  pc_resource_id        VARCHAR(64) NOT NULL,
  name                  VARCHAR(255) NOT NULL,
  resource_model        TINYINT UNSIGNED NOT NULL,
  resource_category_id  INT NULL,
  is_backcountry        BOOLEAN NULL,
  -- The map a site's availability lives under (from its own confirmed
  -- mapIds[] field, captured during catalogSync). Signed for the same
  -- reason as the other pc_*_id columns. Nullable: a small number of
  -- resources (e.g. unstaffed emergency shelters) have no mapIds at all and
  -- simply can't be polled for availability — availabilityPoller skips
  -- those with a warning rather than guessing a map for them.
  map_id                INT NULL,
  last_synced_at        DATETIME NULL,
  created_at            DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_sites_campground_resource (campground_id, pc_resource_id),
  KEY idx_sites_resource_model (resource_model),
  KEY idx_sites_is_backcountry (is_backcountry),
  CONSTRAINT fk_sites_campground
    FOREIGN KEY (campground_id) REFERENCES campgrounds (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Latest known availability per site/date — a cache, not a history log.
-- The poller upserts this on every poll; the diff against the previous
-- `status` value (old row vs. new value, both available before the
-- REPLACE/UPSERT commits) is what drives the 0->1 transition detection.
-- `status` mirrors the Parks Canada enum directly (0/1/3) rather than being
-- reinterpreted into a boolean, so it stays easy to debug against the raw
-- API response.
CREATE TABLE IF NOT EXISTS availability_snapshots (
  site_id     INT UNSIGNED NOT NULL,
  date        DATE NOT NULL,
  status      TINYINT UNSIGNED NOT NULL,
  checked_at  DATETIME NOT NULL,
  PRIMARY KEY (site_id, date),
  KEY idx_availability_snapshots_date (date),
  CONSTRAINT fk_availability_snapshots_site
    FOREIGN KEY (site_id) REFERENCES sites (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- A user's watch request: "notify me if any site at this campground opens
-- up on one of these arrival dates for this many nights." No auth system
-- exists yet (the form UI is email-only, like Trekly's own CampAlert page),
-- so user_id is nullable and unconstrained for now — it's a placeholder for
-- when/if accounts are added, not a live foreign key.
CREATE TABLE IF NOT EXISTS alerts (
  id              INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  user_id         INT UNSIGNED NULL,
  campground_id   INT UNSIGNED NOT NULL,
  arrival_dates   JSON NOT NULL,
  nights          SMALLINT UNSIGNED NOT NULL,
  email           VARCHAR(320) NOT NULL,
  active          BOOLEAN NOT NULL DEFAULT TRUE,
  -- Simplest-to-ship account management: no auth system exists, so
  -- deactivating an alert requires knowing both the email it was created
  -- with and this token (returned once, at creation). Not a substitute for
  -- real auth, just enough to ship a working cancel flow first.
  cancel_token    VARCHAR(36) NOT NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_alerts_campground_active (campground_id, active),
  KEY idx_alerts_email (email),
  CONSTRAINT fk_alerts_campground
    FOREIGN KEY (campground_id) REFERENCES campgrounds (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- Dedupe log: one row per (alert, site, date) notification actually sent.
-- The notifier checks for an existing row before sending; the unique key is
-- what makes that check race-safe under concurrent workers (INSERT ...
-- fails/ignores on duplicate instead of relying on a prior SELECT).
CREATE TABLE IF NOT EXISTS notifications_sent (
  id          INT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  alert_id    INT UNSIGNED NOT NULL,
  site_id     INT UNSIGNED NOT NULL,
  date        DATE NOT NULL,
  sent_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_notifications_sent_alert_site_date (alert_id, site_id, date),
  CONSTRAINT fk_notifications_sent_alert
    FOREIGN KEY (alert_id) REFERENCES alerts (id)
    ON DELETE CASCADE,
  CONSTRAINT fk_notifications_sent_site
    FOREIGN KEY (site_id) REFERENCES sites (id)
    ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
