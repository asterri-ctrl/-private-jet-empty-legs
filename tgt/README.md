# TGT Control Centre template

This folder is a privacy-safe template for a future private TGT repository.

It can generate:
- a trip dashboard (index.html)
- a subscribable itinerary calendar (tgt.ics)
- a cost / booking summary (summary.md)
- cancellation-deadline events in the calendar

## Why the real trip data is not here
This repository is public. Do not commit hotel confirmations, booking references, traveller names, contact details, private addresses, or payment information here.

## Private-repo setup
1. Create a private repository, suggested name: tgt-control-centre.
2. Copy this folder into it.
3. Rename config.example.yaml to config.yaml.
4. Fill in the real trip data.
5. Run python build.py.
6. Add a GitHub Action there if you want automatic rebuilding after config changes.

The engine is intentionally plain YAML + Python so it is easy to update from a phone or laptop.
