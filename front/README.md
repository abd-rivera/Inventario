# Simple Inventory (Frontend)

This frontend now connects to the Flask backend API.

## How to run

1. Start the backend server from [back/app.py](../back/app.py).
2. Open http://localhost:5000 in your browser.

## Features

- Add, edit, delete items
- Search and low-stock filter
- Sort by updated, name, quantity, or value
- CSV import/export

## Notes

- Data is stored in SQLite at back/data/inventory.db.
- CSV columns: id, name, sku, quantity, location, price, threshold, updatedAt
