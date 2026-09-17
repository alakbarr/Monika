# Cycle Summary

{
  "started_at": "2026-08-19T08:46:53.723506+00:00",
  "scraping": {
    "status": "moved to background loop"
  },
  "price_fetch": {
    "XAUUSD/M15": 24,
    "XAUUSD/H1": 6,
    "XAUUSD/H4": 67,
    "XAUUSD/D1": 217,
    "EURUSD/M15": 24,
    "EURUSD/H1": 6,
    "EURUSD/H4": 67,
    "EURUSD/D1": 216,
    "GBPUSD/M15": 24,
    "GBPUSD/H1": 6,
    "GBPUSD/H4": 67,
    "GBPUSD/D1": 216,
    "USDJPY/M15": 24,
    "USDJPY/H1": 6,
    "USDJPY/H4": 67,
    "USDJPY/D1": 216,
    "AUDUSD/M15": 24,
    "AUDUSD/H1": 6,
    "AUDUSD/H4": 67,
    "AUDUSD/D1": 216,
    "XTIUSD/M15": 24,
    "XTIUSD/H1": 6,
    "XTIUSD/H4": 67,
    "XTIUSD/D1": 217,
    "BTCUSD/M15": 24,
    "BTCUSD/H1": 6,
    "BTCUSD/H4": 1,
    "BTCUSD/D1": 100
  },
  "indicators": {
    "XAUUSD/H1": 6404,
    "XAUUSD/H4": 5396,
    "XAUUSD/D1": 5396,
    "EURUSD/H1": 6452,
    "EURUSD/H4": 5396,
    "EURUSD/D1": 5396,
    "GBPUSD/H1": 6452,
    "GBPUSD/H4": 5396,
    "GBPUSD/D1": 5396,
    "USDJPY/H1": 6452,
    "USDJPY/H4": 5396,
    "USDJPY/D1": 5396,
    "AUDUSD/H1": 6452,
    "AUDUSD/H4": 5396,
    "AUDUSD/D1": 5396,
    "XTIUSD/H1": 6404,
    "XTIUSD/H4": 5396,
    "XTIUSD/D1": 5396,
    "BTCUSD/H1": 7028,
    "BTCUSD/H4": 5804,
    "BTCUSD/D1": 5396
  },
  "structure": {
    "XAUUSD/H1": 111,
    "XAUUSD/H4": 107,
    "XAUUSD/D1": 92,
    "EURUSD/H1": 92,
    "EURUSD/H4": 119,
    "EURUSD/D1": 106,
    "GBPUSD/H1": 103,
    "GBPUSD/H4": 109,
    "GBPUSD/D1": 102,
    "USDJPY/H1": 101,
    "USDJPY/H4": 100,
    "USDJPY/D1": 105,
    "AUDUSD/H1": 93,
    "AUDUSD/H4": 109,
    "AUDUSD/D1": 106,
    "XTIUSD/H1": 105,
    "XTIUSD/H4": 93,
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
      "fetched_at": "2026-08-19T08:46:54.724912+00:00"
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
          "short_percent": 72.0,
          "long_percent": 28.0,
          "long_short_ratio": 0.3889
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
      "fetched_at": "2026-08-19T08:47:07.365757+00:00"
    },
    "fxssi_sentiment": {
      "source": "fxssi",
      "ratios": {
        "XTIUSD": {
          "long_percent": 68.55,
          "short_percent": 31.45,
          "long_short_ratio": 2.1797
        },
        "XAUUSD": {
          "long_percent": 60.4,
          "short_percent": 39.6,
          "long_short_ratio": 1.5253
        },
        "EURUSD": {
          "long_percent": 32.39,
          "short_percent": 67.61,
          "long_short_ratio": 0.4791
        },
        "GBPUSD": {
          "long_percent": 38.25,
          "short_percent": 61.75,
          "long_short_ratio": 0.6194
        },
        "USDJPY": {
          "long_percent": 47.48,
          "short_percent": 52.52,
          "long_short_ratio": 0.904
        }
      },
      "fetched_at": "2026-08-19T08:47:20.356851+00:00"
    },
    "vix": {
      "saved": 1
    },
    "fred": {
      "treasury": 0,
      "interest_rates": 0
    },
    "cftc": {
      "saved": 0
    },
    "dxy": {
      "saved": 1
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
      "fetched_at": "2026-08-19T08:48:24.694752+00:00"
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
    "checked_at": "2026-08-19T08:49:12.264321+00:00"
  },
  "macro_regime": {
    "regime": "normal",
    "reason": "",
    "vix": 15.800000190734863
  },
  "api_cost_usd": 0.0,
  "elapsed_total_s": 174.208041
}