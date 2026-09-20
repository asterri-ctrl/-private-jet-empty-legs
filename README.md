# Private Jet Empty Legs → Apple Calendar

One subscribed Apple Calendar feed built from multiple public sources:

- **GlobeAir** — native live iCalendar feed (direct operator)
- **Jetfly** — published PC-12 / PC-24 empty legs (direct operator)
- **PrivJet** — public empty-leg inventory from its operator marketplace
- **AlbaJet** — public empty-leg inventory aggregated from aircraft operators

The generator runs independently for each source, deduplicates overlapping flights, removes expired legs, and writes `docs/empty-legs.ics`.

## Apple Calendar subscription

Once the first workflow run has completed, subscribe to:

`https://raw.githubusercontent.com/asterri-ctrl/-private-jet-empty-legs/main/docs/empty-legs.ics`

On iPhone/iPad: **Calendar → Calendars → Add Calendar → Add Subscription Calendar**, then paste the URL.

## Default behaviour

- Europe-only
- Next 30 days
- Maximum 300 entries
- Calendar events are marked **Free**
- Exact-time flights are timed events
- Availability-window listings are all-day events
- Direct-operator records are preferred over aggregator duplicates

## Notes

Empty legs can change or disappear quickly. Treat the feed as availability radar, not a confirmed flight schedule. Always confirm the current route, time and price with the operator or broker before arranging positioning travel.

Website markup can change. Sources are isolated so one parser failing will not prevent the other sources from updating the feed.
