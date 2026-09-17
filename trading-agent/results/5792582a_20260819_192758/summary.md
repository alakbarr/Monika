# Cycle Summary

{
  "started_at": "2026-08-19T12:24:21.128236+00:00",
  "scraping": {
    "status": "moved to background loop"
  },
  "price_fetch": {
    "XAUUSD/M15": 14,
    "XAUUSD/H1": 4,
    "XAUUSD/H4": 68,
    "XAUUSD/D1": 217,
    "EURUSD/M15": 14,
    "EURUSD/H1": 4,
    "EURUSD/H4": 68,
    "EURUSD/D1": 216,
    "GBPUSD/M15": 14,
    "GBPUSD/H1": 4,
    "GBPUSD/H4": 68,
    "GBPUSD/D1": 216,
    "USDJPY/M15": 14,
    "USDJPY/H1": 4,
    "USDJPY/H4": 68,
    "USDJPY/D1": 216,
    "AUDUSD/M15": 14,
    "AUDUSD/H1": 4,
    "AUDUSD/H4": 68,
    "AUDUSD/D1": 216,
    "XTIUSD/M15": 14,
    "XTIUSD/H1": 4,
    "XTIUSD/H4": 68,
    "XTIUSD/D1": 217,
    "BTCUSD/M15": 14,
    "BTCUSD/H1": 4,
    "BTCUSD/H4": 1,
    "BTCUSD/D1": 100
  },
  "indicators": {
    "XAUUSD/H1": 6452,
    "XAUUSD/H4": 5396,
    "XAUUSD/D1": 5396,
    "EURUSD/H1": 6500,
    "EURUSD/H4": 5396,
    "EURUSD/D1": 5396,
    "GBPUSD/H1": 6500,
    "GBPUSD/H4": 5396,
    "GBPUSD/D1": 5396,
    "USDJPY/H1": 6500,
    "USDJPY/H4": 5396,
    "USDJPY/D1": 5396,
    "AUDUSD/H1": 6500,
    "AUDUSD/H4": 5396,
    "AUDUSD/D1": 5396,
    "XTIUSD/H1": 6452,
    "XTIUSD/H4": 5396,
    "XTIUSD/D1": 5396,
    "BTCUSD/H1": 7076,
    "BTCUSD/H4": 5816,
    "BTCUSD/D1": 5396
  },
  "structure": {
    "XAUUSD/H1": 108,
    "XAUUSD/H4": 107,
    "XAUUSD/D1": 92,
    "EURUSD/H1": 91,
    "EURUSD/H4": 119,
    "EURUSD/D1": 106,
    "GBPUSD/H1": 102,
    "GBPUSD/H4": 109,
    "GBPUSD/D1": 102,
    "USDJPY/H1": 97,
    "USDJPY/H4": 101,
    "USDJPY/D1": 105,
    "AUDUSD/H1": 94,
    "AUDUSD/H4": 111,
    "AUDUSD/D1": 106,
    "XTIUSD/H1": 105,
    "XTIUSD/H4": 94,
    "XTIUSD/D1": 102,
    "BTCUSD/H1": 118,
    "BTCUSD/H4": 108,
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
      "fetched_at": "2026-08-19T12:24:23.325894+00:00"
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
          "short_percent": 44.0,
          "long_percent": 56.0,
          "long_short_ratio": 1.2727
        }
      },
      "fetched_at": "2026-08-19T12:24:37.106508+00:00"
    },
    "fxssi_sentiment": {
      "source": "fxssi",
      "ratios": {
        "XTIUSD": {
          "long_percent": 68.61,
          "short_percent": 31.39,
          "long_short_ratio": 2.1857
        },
        "XAUUSD": {
          "long_percent": 62.76,
          "short_percent": 37.24,
          "long_short_ratio": 1.6853
        },
        "EURUSD": {
          "long_percent": 30.5,
          "short_percent": 69.5,
          "long_short_ratio": 0.4388
        },
        "GBPUSD": {
          "long_percent": 38.38,
          "short_percent": 61.62,
          "long_short_ratio": 0.6228
        },
        "USDJPY": {
          "long_percent": 47.97,
          "short_percent": 52.03,
          "long_short_ratio": 0.922
        }
      },
      "fetched_at": "2026-08-19T12:24:46.867145+00:00"
    },
    "vix": {
      "saved": 0
    },
    "fred": {
      "treasury": 0,
      "interest_rates": 1
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
      "fetched_at": "2026-08-19T12:26:15.395417+00:00"
    }
  },
  "fundamental": {
    "success": false,
    "brief_id": null,
    "tool_calls": 0,
    "elapsed_s": 0.0,
    "input_tokens": 0,
    "output_tokens": 0
  },
  "per_asset": {
    "skipped": true,
    "reason": "fundamental_failed"
  },
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
    "checked_at": "2026-08-19T12:27:20.100333+00:00"
  },
  "macro_regime": {
    "regime": "normal",
    "reason": "",
    "vix": 15.800000190734863
  },
  "api_cost_usd": 0.0,
  "elapsed_total_s": 215.801922
}