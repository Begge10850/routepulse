# RoutePulse v4 deployment and acceptance

## Purpose

Version 4 replaces the long single-page dashboard with one global transport-mode
filter and five conditionally rendered views. It preserves the corrected event
grain, geographic classification, passenger-facing line definitions and
observational wording from earlier versions.

## Snowflake run order

1. Confirm that `09_unique_stop_events.sql`,
   `10_geographic_event_enrichment.sql` and `11_line_focus_models.sql` have
   already completed successfully.
2. Run `12_dashboard_ui_models.sql` in Snowflake. Review all four validation
   result sets before updating the app.
3. Add `environment.yml` to the Streamlit application files so the warehouse
   runtime uses Streamlit 1.52.2.
4. Replace the deployed app's `streamlit_app.py` contents with
   `streamlit_app_v4.py`.
5. Relaunch the app and complete the smoke checks below.

Do not replace the existing deployed app until step 2 finishes successfully.
The v4 application expects the `DASHBOARD_*` transient tables created by that
script.

## Required data evidence

For the unchanged 39.5-hour collection, the all-mode geographic reconciliation
must be:

| Observed stop region | Unique stop events |
|---|---:|
| Berlin | 1,366,027 |
| Brandenburg | 361,516 |
| Outside Berlin-Brandenburg | 3,631 |
| Unmatched/unknown | 24,673 |
| **Total** | **1,755,847** |

All scope rows in validation result 1 must have `EVENT_COUNT_MATCHES = TRUE`.
The event-grain table must remain at 1,755,847 rows. The presentation aggregates
must not change or duplicate the source event table.

## Interface smoke checks

### Header and navigation

- Only Transport mode changes the global analytical scope.
- The mode control contains All modes, Bus, Tram, U-Bahn, S-Bahn and Regional
  rail.
- The three cards show over-five-minute share, P90 delay and delay-data
  availability.
- The denominator sentence defines an observed `stop visit` and says how many
  stop visits contained a delay figure; missing values are explicitly excluded
  rather than treated as zero.
- The first screen states: "Late = reported as more than 5 minutes behind the
  timetable."
- The P90 explanation says "at or below", not "shorter than".
- The engineering strip shows the raw-to-unique event consolidation and zero
  duplicate-key validation.
- Network map, Stations, Lines, When and Data quality are underlined navigation
  choices; changing the view runs only that view's queries.
- The showing caption contains only the selected mode and all-region scope.
- The duplicated mode-rate key finding is absent, and technical definitions are
  inside About the data.

### Network map

- Network map is the default view and adds no second filter.
- It draws one representative scheduled GTFS path per observed passenger-facing
  line, with Berlin and Brandenburg boundaries behind the paths.
- Under All modes, line colour identifies transport mode. Under a specific
  non-bus mode, colour distinguishes passenger-facing lines. Bus remains one
  colour to keep the dense network legible.
- Hover text shows line, operator, mode and scheduled start-to-end description.
- The initial viewport remains in the Berlin-Brandenburg study area even when a
  cross-state route extends farther away.
- The general network map uses a 700-pixel frame so the route network is not
  compressed vertically on a wide desktop.
- Copy states that paths are scheduled routes, not live vehicle movements or a
  delay-severity layer.

### Stations

- Berlin and Brandenburg can be inspected separately without changing the
  global mode scope.
- The page asks "Which stations were late most often?" and explains
  the rate as a count out of every 100 visits with a delay figure.
- The ranking is titled "Stations with the most frequent serious delays" and
  the linked map is titled "Where are these stations?"
- A mode-region combination with no eligible station displays an empty-state
  message.
- Sample counts remain in tooltips rather than crowding axis labels. The dashed
  line is directly labelled with the selected region-and-mode average.
- Bars based on 100–299 visits with a delay figure are paler and described as
  early signals. Low data availability means fewer than 60% of observed visits
  had a delay figure.
- If all ten ranked stations are low sample, the view displays an explicit
  indicative-only warning.
- Map dots are numbered to match the bars, the top three station names are
  shown, and the map explains colour and dot size.
- The takeaway states the late count, denominator, percentage and approximate
  multiple of the selected regional-mode average, with an early-signal warning
  when applicable.

### Lines

- All modes shows only the mode comparison and does not draw route shapes. Its
  heading asks "Which transport modes were late most often?" and its bar labels
  contain only mode names, so it cannot be mistaken for a line ranking.
- A specific mode shows the top ten eligible passenger-facing lines.
- Ranking labels show the line and one start-to-end description without the
  operator; the operator and full direction details remain in tooltips.
- The `See where a line runs` dropdown defaults to None. Selecting a line draws
  one representative scheduled path and its observed stops.
- `Most often late` and `Most late stop visits` appear as two short lists; the
  former rate-versus-volume scatter is absent.
- Paler bars identify limited samples, and tooltips retain the denominator and
  data-availability evidence.
- The takeaway leads with the best-supported high-rate line, then mentions a
  higher raw rate separately when it rests on a limited sample.
- Bus/Regional-rail service-type comparison remains collapsed.

### When

- The chart toggles between over-five-minute share and P90 delay.
- The selected delay measure and event volume appear in two vertically stacked
  panels sharing one time axis; there is no secondary y-axis.
- A day/date band below the hourly ticks clearly labels each observed calendar
  day and identifies the partial first and last days.
- Event volume remains visible as a neutral-colour lower bar panel.
- Hours below 100 visits with a delay figure use hollow grey points/gaps, and the first and
  last partial hours use distinct red diamond markers.
- A headline peak must be a complete hour with at least 100 visits with a delay
  figure.
- The takeaway changes with the measure toggle and identifies its denominator.
- There is no line-by-hour heatmap or heatmap query.

### Data quality

- Regional rows reconcile to the selected-mode KPI total.
- Under All modes, the total is exactly 1,755,847 and the four categories match
  the table above.
- The page does not call 28,304 events "outside"; 24,673 are explicitly
  unmatched/unknown and only 3,631 are outside both states.
- The page asks "How complete is our delay data?" and explains that a shorter
  bar means less is known about actual lateness.
- The full-sample coverage chart groups modes into very complete (>90%), mostly
  complete (75–90%) and partial (<75%) data availability.
- The regional table is labelled for the selected mode. Its unmatched/unknown
  row is grey, and a sentence explains that these stop visits lacked enough
  static-station or coordinate information for a regional assignment but remain
  in totals.
- Potsdam wording identifies line 98 as a line, not a count.
- Limitations state that the sample is one Friday/weekend window, delay values
  are feed predictions and rankings do not establish causes.

## Visual acceptance

Check at 1366×768 and at a standard wide desktop size:

- mode choices remain readable;
- KPI cards do not overlap;
- the view navigation is visible without excessive scrolling;
- charts have readable axis labels and tooltips;
- warning badges are understandable without relying on colour alone;
- maps do not auto-fit to a Europe-wide extent.

## Completion status

Local implementation and static checks are not production validation. The
release is complete only after the SQL validations and interface smoke checks
pass inside the deployed Snowflake Streamlit runtime.
