# Using the app

Sign in with `cenius@cenius.ai` / `cenius` (or click **Use demo credentials**). Every
page is seeded, so nothing needs to be entered before the app is useful.

## Dashboard (`/Dashboard`)

The home screen answers "how is the current run going?" in one glance.

- **Colonising bags** — how many bags are still colonising, against the 14 registered.
- **Mean latest colonisation** — the mean of each active bag's most recent reading.
- **Wet yield · last N days** — total wet weight harvested in the selected window, with a
  delta against the previous window of the same length.
- **Open incidents** — incidents still awaiting a resolution, plus how many are high severity.
- The window selector (**Last 30 / 60 / 90 days**) re-scopes the yield and incident charts.
- **Humidity and CO2 thresholds** strip shows each room's configured range; the link jumps
  to the threshold editor.

## Colonisation (`/Colonisation`)

- Pick a grow room (or *All grow rooms*) to scope the bag cards, the mean figure and the
  trend chart.
- Each bag card shows its strain, room, spawn date, status chip, latest percentage and a
  progress bar.
- Select a bag under **Colonisation trend** to see every reading plotted by date.
- **Record a reading**: choose the bag, the reading date, a percentage between 0 and 100 and
  optional notes. The bag's latest percentage and progress bar update immediately.
- **Register a bag**: bag code, room, strain, substrate recipe, spawn date and a status
  limited to Colonising / Fruiting / Contaminated / Retired (defaults to Colonising).

Validation is inline: a duplicate bag code, a percentage outside 0–100 or a future date
shows a message and writes nothing.

## Flush Yield (`/Flush_Yield`)

- **Strain** and **Window** filters scope the harvest table and the stats; the bar chart
  always compares every strain in the window, sorted by wet yield.
- The line chart plots mean wet weight per flush number for the selected strain, with a
  shaded min–max band across bags.
- The recent-flush table lists harvest date, bag, strain, room, flush number, wet and dry
  weights and the dry/wet ratio of each row.
- **Record a flush**: bag, flush number (pre-filled with the next number for that bag),
  harvest date, wet weight in grams, dry weight in grams and notes. Zero or blank wet
  weight is rejected with an inline message.

## Contamination Log (`/Contamination_Log`)

- Filter the log by grow room, status (Open / Resolved) or contaminant type.
- The table lists date, room, bag, contaminant, severity, status and resolution date.
- **By contaminant type** summarises incidents, how many are still open and how many were
  high severity.
- **Open incident queue** lists every open incident with a **Mark resolved** button. Resolving
  stamps today's date and moves the incident into the resolved view.
- **Log an incident**: room, optional bag (room-wide when none is chosen), incident date,
  contaminant type, severity and the action taken. New incidents start as Open.

## Thresholds (`/Thresholds`)

- Eight seeded rows: one humidity (%) and one CO2 (ppm) row for each of the four rooms.
- The **Metric** filter narrows the table to humidity or CO2.
- **Edit a range**: pick a row, change the minimum and maximum, then save. A minimum that
  is not below the maximum is rejected inline and nothing is written; a valid save shows a
  confirmation, the new values in the table and a fresh `updated_at` stamp that also shows
  up on the dashboard strip.

## Sidebar

Every signed-in page shows the workspace brand, the signed-in operator, **Sign out** and
**Reset demo data**. Reset asks for confirmation, then wipes and reseeds the dataset
(4 rooms, 14 bags, 51 readings, 31 flushes, 8 incidents, 8 thresholds) and reruns the page.
