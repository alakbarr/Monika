# Cycle Summary

{
  "started_at": "2026-08-19T01:43:16.583543+00:00",
  "scraping": {
    "status": "moved to background loop"
  },
  "price_fetch": {
    "XAUUSD/M15": 10,
    "XAUUSD/H1": 2,
    "XAUUSD/H4": 1,
    "XAUUSD/D1": 0,
    "EURUSD/M15": 10,
    "EURUSD/H1": 2,
    "EURUSD/H4": 1,
    "EURUSD/D1": 0,
    "GBPUSD/M15": 10,
    "GBPUSD/H1": 2,
    "GBPUSD/H4": 1,
    "GBPUSD/D1": 0,
    "USDJPY/M15": 10,
    "USDJPY/H1": 2,
    "USDJPY/H4": 1,
    "USDJPY/D1": 0,
    "AUDUSD/M15": 10,
    "AUDUSD/H1": 2,
    "AUDUSD/H4": 1,
    "AUDUSD/D1": 0,
    "XTIUSD/M15": 10,
    "XTIUSD/H1": 2,
    "XTIUSD/H4": 1,
    "XTIUSD/D1": 0,
    "BTCUSD/M15": 10,
    "BTCUSD/H1": 2,
    "BTCUSD/H4": 1,
    "BTCUSD/D1": 0
  },
  "indicators": {
    "XAUUSD/H1": 6320,
    "XAUUSD/H4": 5420,
    "XAUUSD/D1": 5408,
    "EURUSD/H1": 6368,
    "EURUSD/H4": 5420,
    "EURUSD/D1": 5408,
    "GBPUSD/H1": 6368,
    "GBPUSD/H4": 5420,
    "GBPUSD/D1": 5408,
    "USDJPY/H1": 6368,
    "USDJPY/H4": 5420,
    "USDJPY/D1": 5408,
    "AUDUSD/H1": 6368,
    "AUDUSD/H4": 5420,
    "AUDUSD/D1": 5408,
    "XTIUSD/H1": 6320,
    "XTIUSD/H4": 5420,
    "XTIUSD/D1": 5408,
    "BTCUSD/H1": 6944,
    "BTCUSD/H4": 5792,
    "BTCUSD/D1": 5408
  },
  "structure": {
    "XAUUSD/H1": 112,
    "XAUUSD/H4": 106,
    "XAUUSD/D1": 92,
    "EURUSD/H1": 91,
    "EURUSD/H4": 118,
    "EURUSD/D1": 106,
    "GBPUSD/H1": 105,
    "GBPUSD/H4": 109,
    "GBPUSD/D1": 102,
    "USDJPY/H1": 99,
    "USDJPY/H4": 100,
    "USDJPY/D1": 105,
    "AUDUSD/H1": 94,
    "AUDUSD/H4": 110,
    "AUDUSD/D1": 106,
    "XTIUSD/H1": 105,
    "XTIUSD/H4": 94,
    "XTIUSD/D1": 102,
    "BTCUSD/H1": 118,
    "BTCUSD/H4": 109,
    "BTCUSD/D1": 82
  },
  "data_refresh": {
    "btc_funding": {
      "error": "Coinglass API unavailable"
    },
    "binance_sentiment": {
      "source": "binance_futures",
      "ratios": {
        "BTCUSDT": {
          "long_percent": 57.940000000000005,
          "short_percent": 42.059999999999995,
          "long_short_ratio": 1.3776
        },
        "ETHUSDT": {
          "long_percent": 69.19999999999999,
          "short_percent": 30.8,
          "long_short_ratio": 2.2468
        }
      },
      "fetched_at": "2026-08-19T01:43:22.449353+00:00"
    },
    "myfxbook_sentiment": {
      "source": "myfxbook",
      "ratios": {
        "EURUSD": {
          "short_percent": 63.0,
          "long_percent": 37.0,
          "long_short_ratio": 0.5873
        },
        "GBPUSD": {
          "short_percent": 71.0,
          "long_percent": 29.0,
          "long_short_ratio": 0.4085
        },
        "USDJPY": {
          "short_percent": 58.0,
          "long_percent": 42.0,
          "long_short_ratio": 0.7241
        },
        "XAUUSD": {
          "short_percent": 43.0,
          "long_percent": 57.0,
          "long_short_ratio": 1.3256
        }
      },
      "fetched_at": "2026-08-19T01:43:31.098086+00:00"
    },
    "fxssi_sentiment": {
      "source": "fxssi",
      "ratios": {
        "XTIUSD": {
          "long_percent": 70.09,
          "short_percent": 29.91,
          "long_short_ratio": 2.3434
        },
        "XAUUSD": {
          "long_percent": 63.8,
          "short_percent": 36.2,
          "long_short_ratio": 1.7624
        },
        "EURUSD": {
          "long_percent": 37.22,
          "short_percent": 62.78,
          "long_short_ratio": 0.5929
        },
        "GBPUSD": {
          "long_percent": 39.35,
          "short_percent": 60.65,
          "long_short_ratio": 0.6488
        },
        "USDJPY": {
          "long_percent": 46.58,
          "short_percent": 53.42,
          "long_short_ratio": 0.872
        }
      },
      "fetched_at": "2026-08-19T01:43:43.194626+00:00"
    },
    "vix": {
      "saved": 0
    },
    "fred": {
      "treasury": 0,
      "interest_rates": 0
    },
    "cftc": {
      "saved": 0
    },
    "dxy": {
      "saved": 0
    },
    "fear_greed": {
      "value": 46,
      "classification": "Fear"
    },
    "eia_oil": {
      "latest_inventory_mbbl": 424.41,
      "latest_period": "2026-08-07",
      "wow_change_mbbl": 17.42,
      "trend": "build",
      "market_signal": "bearish_supply",
      "history_5w": [
        {
          "period": "2026-08-07",
          "value_mbbl": 424.41
        },
        {
          "period": "2026-07-31",
          "value_mbbl": 406.99
        },
        {
          "period": "2026-07-24",
          "value_mbbl": 404.51
        },
        {
          "period": "2026-07-17",
          "value_mbbl": 411.68
        },
        {
          "period": "2026-07-10",
          "value_mbbl": 409.67
        }
      ],
      "fetched_at": "2026-08-19T01:44:22.619297+00:00"
    }
  },
  "fundamental": {},
  "per_asset": {},
  "price_fetch_m15": {
    "XAUUSD/M15": 0,
    "EURUSD/M15": 0,
    "GBPUSD/M15": 0,
    "USDJPY/M15": 0,
    "AUDUSD/M15": 0,
    "XTIUSD/M15": 0,
    "BTCUSD/M15": 0
  },
  "gemini_precompute": "success",
  "performance_notes": {
    "regenerated": false,
    "reason": "insufficient_data (0/15 trades)"
  },
  "data_validation": {
    "ready": true,
    "warnings": [],
    "errors": [],
    "checked_at": "2026-08-19T01:45:12.885244+00:00"
  },
  "macro_regime": {
    "regime": "normal",
    "reason": "",
    "vix": 15.8100004196167
  },
  "elapsed_total_s": 150.243384
}