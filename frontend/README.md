# PayGent Dashboard

Next.js frontend for the PayGent Lightning marketplace. Displays live service listings, payment feed, and marketplace stats — auto-refreshes every 3 seconds.

## Prerequisites

Backend must be running on `http://localhost:8000`. See the [root README](../README.md) for setup.

## Running

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Structure

```
app/
  page.tsx          Main dashboard (client component, 3s polling)
  layout.tsx        Root layout
  globals.css       Tailwind base + dark background

components/
  StatsBar.tsx      Volume / fees / calls / balance cards
  ServiceCatalog.tsx  Active services with icons, descriptions, prices
  TransactionFeed.tsx  Live payment history with relative timestamps

lib/
  api.ts            fetchStats / fetchServices / fetchTransactions
```

## Environment

Set `NEXT_PUBLIC_API_URL` to override the default backend URL:

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```
