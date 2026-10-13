# Known issues / open questions

Durable record of things found during live testing that weren't silently
resolved — either fixed with the reasoning noted, or left open pending your
input, per the project's own standard of flagging rather than guessing.

## Open: resourceModel:0 sites may be wrongly excluded in ~8 parks

**Status:** unresolved, filter not changed.

`catalogSync.js` only keeps `resourceModel === 2` sites, per the originally
confirmed enum (`2 = real bookable site, 3 = trailhead/access-point, 0 =
grazing/horse zone`). Live testing (see conversation, live run against
`/api/resourceLocation` + `/resourcelocation/resources`) found that 8 of the
15 matched backcountry locations return **zero** `resourceModel===2` sites:

- Fundy, Gulf Islands, Riding Mountain, Terra Nova, Kejimkujik, Georgian Bay
  Islands, Cape Breton Highlands, Bruce Peninsula

In every one of these, **100% of resource entries are `resourceModel: 0`**,
but their names look like real numbered backcountry sites, not grazing/horse
zones — e.g. Fundy: `SH01`, `RC01`-`RC03`, `CM1`/`CM2`, `TL11`/`TL12`;
Kejimkujik: plain numbers like `17`, `41`, `42`.

Direct test on Kejimkujik site `17` (resourceId `-2147483466`):
- Has a real `mapIds` array and a `feeScheduleId` (suggesting a genuine,
  fee-charging bookable unit)
- `/availability/map` returns live data for it
- The returned `availability` value is **`5`** — outside the confirmed
  `0 | 1 | 3` enum entirely

**What this means:** `resourceModel` semantics likely aren't uniform across
all parks the way they are for Banff/Jasper (where they were originally
confirmed), and/or `5` is a legitimate status this service doesn't yet
interpret. The current filter is probably silently excluding a meaningful
number of real Eastern-Canada backcountry sites (Fundy alone had 14
candidates, all currently dropped).

**Deliberately not done:** changing the `resourceModel===2` filter, or
guessing what `availability: 5` means. Both are confirmed API semantics from
the original spec; changing them requires either checking a live site on
reservation.pc.gc.ca or new confirmation from you, not a guess on my part.

**Blast radius today:** none of the currently-synced 179 sites (Jasper,
Banff/Kootenay/Yoho, Waterton Lakes, Yoho-Lake O'Hara, Kouchibouguac, Gros
Morne, Forillon) are `resourceModel: 0` sites, so `availabilityPoller.js`
never encounters an `availability: 5` value in practice right now. If the
filter is ever loosened to include `resourceModel: 0`, the poller's diff
logic (`oldStatus === 0 && newStatus === 1`) will simply never fire for a
site stuck at `5` — it won't crash, it'll just never notify on it, which is
a safe default but likely not the intended behavior once this is resolved.

## Fixed: dotenv load-order bug in the DB pool

**Status:** fixed.

`src/db/pool.js` called `mysql.createPool()` using `process.env.*` at
module-load time. `catalogSync.js` required `pool.js` at the top of the
file, before its own CLI-runner block called `dotenv.config()` — so on a
standalone run (`node src/jobs/catalogSync.js`), the pool was created with
all-undefined credentials, failing with
`Access denied for user ''@'...' (using password: NO)` on the first DB
write.

Fix: `pool.js` now calls `require("dotenv").config()` at its own top, so
env vars are guaranteed loaded regardless of what requires it or in what
order. Removed the now-redundant `dotenv.config()` call from
`catalogSync.js`'s CLI block.
