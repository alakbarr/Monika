# Cycle Summary

{
  "started_at": "2026-08-19T13:19:34.125940+00:00",
  "scraping": {
    "status": "moved to background loop"
  },
  "price_fetch": {
    "XAUUSD/M15": 1,
    "XAUUSD/H1": 0,
    "XAUUSD/H4": 67,
    "XAUUSD/D1": 217,
    "EURUSD/M15": 1,
    "EURUSD/H1": 0,
    "EURUSD/H4": 67,
    "EURUSD/D1": 216,
    "GBPUSD/M15": 1,
    "GBPUSD/H1": 0,
    "GBPUSD/H4": 67,
    "GBPUSD/D1": 216,
    "USDJPY/M15": 1,
    "USDJPY/H1": 0,
    "USDJPY/H4": 67,
    "USDJPY/D1": 216,
    "AUDUSD/M15": 1,
    "AUDUSD/H1": 0,
    "AUDUSD/H4": 67,
    "AUDUSD/D1": 216,
    "XTIUSD/M15": 1,
    "XTIUSD/H1": 0,
    "XTIUSD/H4": 67,
    "XTIUSD/D1": 217,
    "BTCUSD/M15": 1,
    "BTCUSD/H1": 0,
    "BTCUSD/H4": 0,
    "BTCUSD/D1": 100
  },
  "indicators": {
    "XAUUSD/H1": 6464,
    "XAUUSD/H4": 5396,
    "XAUUSD/D1": 5396,
    "EURUSD/H1": 6512,
    "EURUSD/H4": 5396,
    "EURUSD/D1": 5396,
    "GBPUSD/H1": 6512,
    "GBPUSD/H4": 5396,
    "GBPUSD/D1": 5396,
    "USDJPY/H1": 6512,
    "USDJPY/H4": 5396,
    "USDJPY/D1": 5396,
    "AUDUSD/H1": 6512,
    "AUDUSD/H4": 5396,
    "AUDUSD/D1": 5396,
    "XTIUSD/H1": 6464,
    "XTIUSD/H4": 5396,
    "XTIUSD/D1": 5396,
    "BTCUSD/H1": 7088,
    "BTCUSD/H4": 5828,
    "BTCUSD/D1": 5396
  },
  "structure": {
    "XAUUSD/H1": 107,
    "XAUUSD/H4": 104,
    "XAUUSD/D1": 92,
    "EURUSD/H1": 91,
    "EURUSD/H4": 119,
    "EURUSD/D1": 106,
    "GBPUSD/H1": 102,
    "GBPUSD/H4": 109,
    "GBPUSD/D1": 102,
    "USDJPY/H1": 98,
    "USDJPY/H4": 100,
    "USDJPY/D1": 105,
    "AUDUSD/H1": 92,
    "AUDUSD/H4": 107,
    "AUDUSD/D1": 106,
    "XTIUSD/H1": 105,
    "XTIUSD/H4": 94,
    "XTIUSD/D1": 102,
    "BTCUSD/H1": 117,
    "BTCUSD/H4": 107,
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
      "fetched_at": "2026-08-19T13:22:14.293734+00:00"
    },
    "myfxbook_sentiment": {
      "source": "myfxbook",
      "ratios": {
        "EURUSD": {
          "short_percent": 64.0,
          "long_percent": 36.0,
          "long_short_ratio": 0.5625
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
          "short_percent": 42.0,
          "long_percent": 58.0,
          "long_short_ratio": 1.381
        }
      },
      "fetched_at": "2026-08-19T13:22:22.802404+00:00"
    },
    "fxssi_sentiment": {
      "source": "fxssi",
      "ratios": {
        "XTIUSD": {
          "long_percent": 68.56,
          "short_percent": 31.44,
          "long_short_ratio": 2.1807
        },
        "XAUUSD": {
          "long_percent": 57.72,
          "short_percent": 42.28,
          "long_short_ratio": 1.3652
        },
        "EURUSD": {
          "long_percent": 28.06,
          "short_percent": 71.94,
          "long_short_ratio": 0.39
        },
        "GBPUSD": {
          "long_percent": 35.52,
          "short_percent": 64.48,
          "long_short_ratio": 0.5509
        },
        "USDJPY": {
          "long_percent": 50.29,
          "short_percent": 49.71,
          "long_short_ratio": 1.0117
        }
      },
      "fetched_at": "2026-08-19T13:22:34.696511+00:00"
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
      "fetched_at": "2026-08-19T13:23:47.771737+00:00"
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
    "checked_at": "2026-08-19T13:24:48.789429+00:00"
  },
  "macro_regime": {
    "regime": "normal",
    "reason": "",
    "vix": 15.800000190734863
  },
  "api_cost_usd": 0.0,
  "elapsed_total_s": 718.4493
}