"""
Script to generate standalone interactive HTML quadrant visualization for LLM models.
Source: model_all.csv
Output: model_quadrant_analysis.html
"""

import csv
import json
import os
import statistics
from pathlib import Path


def clean_num(val: str, default: float = 0.0) -> float:
    if not val or val.strip() == "":
        return default
    s = val.strip().replace("$", "").replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return default


def parse_csv(filepath: str):
    models = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            cost = clean_num(row.get("Estimate Cost per Task", "0"))
            score = clean_num(row.get("Weightened Average", "0"))
            eff = clean_num(row.get("Cost Efficient", "0"))
            tokens = clean_num(row.get("Estimate Token Output per Task", "0"))
            
            models.append({
                "id": idx + 1,
                "provider": row.get("Provider", "").strip(),
                "model": row.get("Model", "").strip(),
                "thinking": row.get("Thinking Level", "").strip(),
                "cost": cost,
                "score": score,
                "cost_efficient": eff,
                "tokens": tokens,
                "input_price": row.get("Input", "").strip(),
                "cache_price": row.get("Cache Input", "").strip(),
                "output_price": row.get("Output", "").strip(),
                "aa_economics": clean_num(row.get("AA-Economics", "0")),
                "aa_strategy": clean_num(row.get("AA-Strategy & Ops", "0")),
                "aa_finance": clean_num(row.get("AA-Finance & Accounting", "0")),
                "aa_agentic": clean_num(row.get("AA-Agentic", "0")),
            })
    return models


def compute_stats(models):
    scores = [m["score"] for m in models]
    costs = [m["cost"] for m in models]
    
    return {
        "count": len(models),
        "score_min": min(scores),
        "score_max": max(scores),
        "score_mean": round(statistics.mean(scores), 2),
        "score_median": round(statistics.median(scores), 2),
        "score_midrange": round((min(scores) + max(scores)) / 2, 2),
        "cost_min": min(costs),
        "cost_max": max(costs),
        "cost_mean": round(statistics.mean(costs), 4),
        "cost_median": round(statistics.median(costs), 4),
        "cost_midrange": round((min(costs) + max(costs)) / 2, 4),
    }


def generate_html(models, stats, output_path: str):
    data_json = json.dumps(models, ensure_ascii=False)
    stats_json = json.dumps(stats, ensure_ascii=False)

    html_content = f"""<!DOCTYPE html>
<html lang="id" class="dark">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Analisis Kuadran Model LLM - Performa vs Biaya</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {{
      darkMode: 'class',
      theme: {{
        extend: {{
          fontFamily: {{
            sans: ['"Plus Jakarta Sans"', 'sans-serif'],
          }},
          colors: {{
            brand: {{
              50: '#ecfdf5',
              100: '#d1fae5',
              400: '#34d399',
              500: '#10b981',
              600: '#059669',
              900: '#064e3b',
            }},
            dark: {{
              800: '#1e293b',
              850: '#151f32',
              900: '#0f172a',
              950: '#090d16',
            }}
          }}
        }}
      }}
    }}
  </script>
  <style>
    body {{
      font-family: 'Plus Jakarta Sans', sans-serif;
      background-color: #090d16;
      color: #f1f5f9;
    }}
    .glow-sweetspot {{
      box-shadow: 0 0 25px -5px rgba(16, 185, 129, 0.35);
    }}
    .custom-scrollbar::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    .custom-scrollbar::-webkit-scrollbar-track {{
      background: #0f172a;
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb {{
      background: #334155;
      border-radius: 4px;
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb:hover {{
      background: #475569;
    }}
  </style>
</head>
<body class="min-h-screen bg-dark-950 text-slate-100 antialiased p-3 sm:p-6 lg:p-8 custom-scrollbar">

  <!-- Toast Notification -->
  <div id="toastNotification" class="fixed bottom-5 right-5 z-50 transform translate-y-16 opacity-0 transition-all duration-300 pointer-events-none bg-slate-900 border border-emerald-500/50 text-emerald-300 px-4 py-2.5 rounded-xl shadow-2xl flex items-center gap-2 text-xs font-semibold">
    <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
    <span id="toastMessage">Threshold berhasil diperbarui!</span>
  </div>

  <!-- Header Section -->
  <header class="max-w-7xl mx-auto mb-5">
    <div class="flex flex-col md:flex-row md:items-center md:justify-between gap-4 border-b border-slate-800/80 pb-5">
      <div>
        <div class="flex items-center gap-2 mb-1.5">
          <span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
            LLM Performance & Cost Matrix
          </span>
          <span class="text-xs text-slate-400">| Sumber: <code class="text-slate-300">model_all.csv</code></span>
        </div>
        <h1 class="text-2xl sm:text-3xl font-extrabold tracking-tight text-white flex items-center gap-2">
          Kuadran Evaluasi Model LLM
        </h1>
        <p class="text-sm text-slate-400 mt-1 max-w-3xl">
          Pemetaan 2D model LLM: <strong>Weighted Average Score</strong> (Sumbu Y) vs <strong>Estimate Cost per Task ($)</strong> (Sumbu X) dengan titik tengah dinamis dan sorotan khusus pada <span class="text-emerald-400 font-semibold underline decoration-emerald-500/50">Kuadran Skor Tinggi & Biaya Rendah (Sweet Spot)</span>.
        </p>
      </div>

      <div class="flex flex-wrap items-center gap-2">
        <button id="btnExportPng" class="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition flex items-center gap-1.5">
          <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
          Export PNG
        </button>
        <button id="btnExportCsv" class="px-3.5 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-medium border border-slate-700 transition flex items-center gap-1.5">
          <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg>
          Export CSV
        </button>
      </div>
    </div>
  </header>

  <main class="max-w-7xl mx-auto space-y-5">

    <!-- KPI Summary Cards -->
    <section class="grid grid-cols-2 lg:grid-cols-5 gap-3 sm:gap-4">
      <!-- Card 1: Total Models -->
      <div class="bg-dark-900/90 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-slate-400">Total Evaluasi</span>
          <span class="p-1.5 rounded-lg bg-blue-500/10 text-blue-400 text-xs">📊 Models</span>
        </div>
        <div class="mt-2">
          <div class="text-2xl sm:text-3xl font-bold text-white" id="kpiTotalModels">72</div>
          <p class="text-xs text-slate-500 mt-0.5">Konfigurasi Model LLM</p>
        </div>
      </div>

      <!-- Card 2: Sweet Spot Models (Highlighted) -->
      <div class="bg-gradient-to-br from-emerald-950/40 via-dark-900 to-dark-900 border border-emerald-500/40 rounded-xl p-4 flex flex-col justify-between glow-sweetspot relative overflow-hidden">
        <div class="absolute -right-6 -bottom-6 w-24 h-24 bg-emerald-500/10 rounded-full blur-xl pointer-events-none"></div>
        <div class="flex items-center justify-between">
          <span class="text-xs font-bold text-emerald-400 flex items-center gap-1">
            ⭐ Sweet Spot
          </span>
          <span class="px-2 py-0.5 rounded text-[10px] font-extrabold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
            TARGET
          </span>
        </div>
        <div class="mt-2">
          <div class="flex items-baseline gap-2">
            <span class="text-2xl sm:text-3xl font-extrabold text-emerald-400" id="kpiSweetSpotCount">9</span>
            <span class="text-xs text-emerald-300/80 font-medium" id="kpiSweetSpotPercent">(12.5%)</span>
          </div>
          <p class="text-xs text-emerald-200/60 mt-0.5">Skor Tinggi & Biaya Rendah</p>
        </div>
      </div>

      <!-- Card 3: Top Value Pick -->
      <div class="bg-dark-900/90 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-slate-400">Top Skor di Sweet Spot</span>
          <span class="p-1.5 rounded-lg bg-purple-500/10 text-purple-400 text-xs">🏆 Best</span>
        </div>
        <div class="mt-2">
          <div class="text-lg font-bold text-slate-100 truncate" id="kpiTopScoreModel">-</div>
          <p class="text-xs text-slate-400 mt-0.5" id="kpiTopScoreDetail">Skor: - | Cost: -</p>
        </div>
      </div>

      <!-- Card 4: Lowest Cost in Sweet Spot -->
      <div class="bg-dark-900/90 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-slate-400">Termurah di Sweet Spot</span>
          <span class="p-1.5 rounded-lg bg-cyan-500/10 text-cyan-400 text-xs">⚡ Budget</span>
        </div>
        <div class="mt-2">
          <div class="text-lg font-bold text-slate-100 truncate" id="kpiLowestCostModel">-</div>
          <p class="text-xs text-slate-400 mt-0.5" id="kpiLowestCostDetail">Cost: - | Skor: -</p>
        </div>
      </div>

      <!-- Card 5: Center Point Thresholds -->
      <div class="col-span-2 lg:col-span-1 bg-dark-900/90 border border-slate-800 rounded-xl p-4 flex flex-col justify-between">
        <div class="flex items-center justify-between">
          <span class="text-xs font-medium text-slate-400">Titik Tengah Aktif</span>
          <span class="px-2 py-0.5 rounded text-[10px] font-semibold bg-slate-800 text-slate-300" id="kpiCenterMode">Median</span>
        </div>
        <div class="mt-2 text-xs space-y-1">
          <div class="flex justify-between items-center">
            <span class="text-slate-400">Sumbu Skor (Y):</span>
            <span class="font-bold text-emerald-400" id="kpiScoreThreshold">44.95</span>
          </div>
          <div class="flex justify-between items-center">
            <span class="text-slate-400">Sumbu Cost (X):</span>
            <span class="font-bold text-amber-400" id="kpiCostThreshold">$0.1150</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ENHANCED THRESHOLD CONTROL PANEL (Always Prominent & Fast) -->
    <section class="bg-gradient-to-b from-dark-900 to-dark-950 border border-slate-700/80 rounded-xl p-4 sm:p-5 shadow-xl space-y-4">
      <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3 border-b border-slate-800/80 pb-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center gap-1.5">
            <svg class="w-4 h-4 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"></path></svg>
            Kustomisasi Titik Tengah (Thresholds)
          </span>
          <span id="liveCounterPill" class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30">
            🎯 9 model di Sweet Spot
          </span>
        </div>

        <!-- Strategy Presets & Click Toggle -->
        <div class="flex flex-wrap items-center gap-1.5">
          <span class="text-[11px] font-semibold text-slate-400 mr-1">Preset Cepat:</span>
          <button data-preset="median" class="preset-btn px-2.5 py-1 text-xs font-bold rounded-lg transition bg-emerald-600 text-white shadow">
            Median (50%)
          </button>
          <button data-preset="mean" class="preset-btn px-2.5 py-1 text-xs font-medium rounded-lg transition bg-slate-800 text-slate-300 hover:bg-slate-700">
            Mean (Avg)
          </button>
          <button data-preset="elite" class="preset-btn px-2.5 py-1 text-xs font-medium rounded-lg transition bg-slate-800 text-slate-300 hover:bg-slate-700">
            ⭐ Elite (≥50, ≤$0.15)
          </button>
          <button data-preset="budget" class="preset-btn px-2.5 py-1 text-xs font-medium rounded-lg transition bg-slate-800 text-slate-300 hover:bg-slate-700">
            ⚡ Budget (≥45, ≤$0.05)
          </button>
          <button data-preset="balanced" class="preset-btn px-2.5 py-1 text-xs font-medium rounded-lg transition bg-slate-800 text-slate-300 hover:bg-slate-700">
            🛡️ Balanced (≥46, ≤$0.10)
          </button>

          <!-- Click-on-Chart Mode Toggle -->
          <button id="btnToggleClickMode" class="ml-1.5 px-2.5 py-1 text-xs font-medium rounded-lg transition border border-slate-700 bg-slate-800/80 text-slate-300 hover:border-emerald-500 flex items-center gap-1">
            <span class="w-2 h-2 rounded-full bg-slate-500" id="clickModeIndicator"></span>
            <span>Klik Grafik: <strong id="clickModeText">OFF</strong></span>
          </button>
        </div>
      </div>

      <!-- Direct Numeric Inputs + Sliders + Quick Steppers -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 sm:gap-6">
        <!-- SCORE CONTROLS (Y) -->
        <div class="bg-dark-900/90 border border-slate-800 rounded-xl p-3.5 space-y-2.5">
          <div class="flex items-center justify-between">
            <label for="numScore" class="text-xs font-bold text-slate-200 flex items-center gap-1.5">
              <span class="w-2 h-2 rounded bg-emerald-400"></span>
              Batas Skor Minimum (Sumbu Y)
            </label>
            <div class="flex items-center gap-1">
              <input 
                id="numScore" 
                type="number" 
                min="20.0" 
                max="62.0" 
                step="0.25" 
                value="44.95" 
                class="w-24 bg-dark-950 border border-slate-700 focus:border-emerald-500 focus:outline-none rounded-lg px-2.5 py-1 text-right text-xs font-bold text-emerald-400 font-mono"
              />
              <span class="text-xs text-slate-400">pts</span>
            </div>
          </div>

          <!-- Stepper Buttons -->
          <div class="flex items-center justify-between gap-1 text-[11px]">
            <span class="text-slate-500">Fine-tune:</span>
            <div class="inline-flex rounded-lg bg-dark-950 p-0.5 border border-slate-800 gap-1">
              <button data-step-score="-1.0" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono">-1.0</button>
              <button data-step-score="-0.25" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono">-0.25</button>
              <button data-step-score="+0.25" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 font-mono">+0.25</button>
              <button data-step-score="+1.0" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-emerald-400 font-mono">+1.0</button>
            </div>
          </div>

          <!-- Range Slider -->
          <div class="space-y-1 pt-1">
            <input 
              id="rangeScore" 
              type="range" 
              min="21.9" 
              max="59.15" 
              step="0.05" 
              value="44.95" 
              class="w-full accent-emerald-500 bg-slate-800 rounded-lg cursor-pointer h-2" 
            />
            <div class="flex justify-between text-[10px] text-slate-500 font-mono">
              <span>Min: 21.90</span>
              <span>Median: 44.95</span>
              <span>Max: 59.15</span>
            </div>
          </div>
        </div>

        <!-- COST CONTROLS (X) -->
        <div class="bg-dark-900/90 border border-slate-800 rounded-xl p-3.5 space-y-2.5">
          <div class="flex items-center justify-between">
            <label for="numCost" class="text-xs font-bold text-slate-200 flex items-center gap-1.5">
              <span class="w-2 h-2 rounded bg-amber-400"></span>
              Batas Biaya Maksimum (Sumbu X)
            </label>
            <div class="flex items-center gap-1">
              <span class="text-xs text-slate-400 font-bold">$</span>
              <input 
                id="numCost" 
                type="number" 
                min="0.000" 
                max="1.850" 
                step="0.005" 
                value="0.115" 
                class="w-24 bg-dark-950 border border-slate-700 focus:border-amber-500 focus:outline-none rounded-lg px-2.5 py-1 text-right text-xs font-bold text-amber-400 font-mono"
              />
            </div>
          </div>

          <!-- Stepper Buttons -->
          <div class="flex items-center justify-between gap-1 text-[11px]">
            <span class="text-slate-500">Fine-tune:</span>
            <div class="inline-flex rounded-lg bg-dark-950 p-0.5 border border-slate-800 gap-1">
              <button data-step-cost="-0.05" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono">-$0.05</button>
              <button data-step-cost="-0.01" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 font-mono">-$0.01</button>
              <button data-step-cost="+0.01" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-400 font-mono">+$0.01</button>
              <button data-step-cost="+0.05" class="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-amber-400 font-mono">+$0.05</button>
            </div>
          </div>

          <!-- Range Slider -->
          <div class="space-y-1 pt-1">
            <input 
              id="rangeCost" 
              type="range" 
              min="0.000" 
              max="1.800" 
              step="0.005" 
              value="0.115" 
              class="w-full accent-amber-500 bg-slate-800 rounded-lg cursor-pointer h-2" 
            />
            <div class="flex justify-between text-[10px] text-slate-500 font-mono">
              <span>Min: $0.00</span>
              <span>Median: $0.115</span>
              <span>Max: $1.80</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Filters: Provider, Thinking Level, Scale -->
      <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pt-2 border-t border-slate-800/80 text-xs">
        <!-- Provider pills -->
        <div class="flex flex-wrap items-center gap-1.5" id="providerFilterContainer">
          <span class="font-semibold text-slate-400 mr-1">Provider:</span>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <!-- Thinking Level pills -->
          <div class="flex flex-wrap items-center gap-1.5" id="thinkingFilterContainer">
            <span class="font-semibold text-slate-400 mr-1">Thinking:</span>
          </div>

          <!-- Scale Switcher -->
          <div class="flex items-center gap-1.5 pl-2 border-l border-slate-800">
            <span class="text-slate-400">Skala X:</span>
            <div class="inline-flex rounded-lg bg-dark-950 p-0.5 border border-slate-800" id="scaleGroup">
              <button data-scale="linear" class="px-2 py-0.5 text-xs font-semibold rounded bg-slate-700 text-white">Linear</button>
              <button data-scale="log" class="px-2 py-0.5 text-xs font-medium rounded text-slate-400 hover:text-white">Log</button>
            </div>
          </div>

          <!-- Reset Button -->
          <button id="btnResetFilters" class="text-xs text-slate-400 hover:text-emerald-400 underline transition">
            Reset Default
          </button>
        </div>
      </div>
    </section>

    <!-- Chart Container with Quadrant Overlays -->
    <section class="bg-dark-900/90 border border-slate-800 rounded-xl p-4 sm:p-5 relative">
      <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3 pb-2 border-b border-slate-800/60">
        <div class="flex items-center gap-2">
          <span class="w-2.5 h-2.5 rounded-full bg-emerald-400"></span>
          <h2 class="text-sm sm:text-base font-bold text-white">Scatter Plot Kuadran: Weighted Average Score vs Estimate Cost per Task</h2>
          <span id="clickModeChartBadge" class="hidden px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/30 animate-pulse">
            🎯 Klik titik mana pun pada diagram untuk memindahkan garis titik tengah
          </span>
        </div>
        <div class="flex items-center gap-3 text-xs text-slate-400">
          <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-emerald-500/20 border border-emerald-500"></span> Sweet Spot</span>
          <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-indigo-500/20 border border-indigo-500"></span> Premium</span>
          <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-amber-500/20 border border-amber-500"></span> Budget Utility</span>
          <span class="flex items-center gap-1"><span class="inline-block w-3 h-3 rounded bg-rose-500/20 border border-rose-500"></span> Underperformers</span>
        </div>
      </div>

      <!-- Quadrant Guide Badges -->
      <div class="grid grid-cols-2 gap-2 text-[11px] mb-2 px-1">
        <div class="p-2 rounded-lg bg-emerald-950/30 border border-emerald-500/30 text-emerald-300 flex items-center justify-between">
          <span class="font-bold flex items-center gap-1.5">
            ⭐ KUADRAN I (KIRI ATAS): THE SWEET SPOT
          </span>
          <span class="text-[10px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.5 rounded">Skor ≥ Batas & Biaya ≤ Batas</span>
        </div>
        <div class="p-2 rounded-lg bg-indigo-950/30 border border-indigo-500/20 text-indigo-300 flex items-center justify-between">
          <span class="font-bold flex items-center gap-1.5">
            🚀 KUADRAN II (KANAN ATAS): PREMIUM TIER
          </span>
          <span class="text-[10px] text-indigo-400 bg-indigo-500/10 px-1.5 py-0.5 rounded">Skor ≥ Batas & Biaya &gt; Batas</span>
        </div>
      </div>

      <!-- ECharts Canvas -->
      <div id="quadrantChart" style="width: 100%; height: 600px;"></div>

      <div class="grid grid-cols-2 gap-2 text-[11px] mt-2 px-1">
        <div class="p-2 rounded-lg bg-amber-950/30 border border-amber-500/20 text-amber-300 flex items-center justify-between">
          <span class="font-bold flex items-center gap-1.5">
            💡 KUADRAN III (KIRI BAWAH): BUDGET UTILITY
          </span>
          <span class="text-[10px] text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded">Skor &lt; Batas & Biaya ≤ Batas</span>
        </div>
        <div class="p-2 rounded-lg bg-rose-950/30 border border-rose-500/20 text-rose-300 flex items-center justify-between">
          <span class="font-bold flex items-center gap-1.5">
            ⚠️ KUADRAN IV (KANAN BAWAH): UNDERPERFORMERS
          </span>
          <span class="text-[10px] text-rose-400 bg-rose-500/10 px-1.5 py-0.5 rounded">Skor &lt; Batas & Biaya &gt; Batas</span>
        </div>
      </div>
    </section>

    <!-- Data Table & Drilldown Section -->
    <section class="bg-dark-900/90 border border-slate-800 rounded-xl p-4 sm:p-5 space-y-4">
      <div class="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h3 class="text-base font-bold text-white flex items-center gap-2">
            <span>Daftar Model Berdasarkan Kuadran</span>
            <span class="px-2 py-0.5 text-xs rounded bg-slate-800 text-slate-300 font-normal" id="tableFilteredCount">72 model</span>
          </h3>
          <p class="text-xs text-slate-400 mt-0.5">Filter, klik baris untuk fokus di grafik, atau klik "🎯 Patokan" untuk menjadikan nilai model sebagai titik tengah.</p>
        </div>

        <div class="flex flex-wrap items-center gap-2">
          <!-- Search box -->
          <div class="relative">
            <input id="searchInput" type="text" placeholder="Cari model / provider..." class="bg-dark-950 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500 w-52" />
          </div>

          <!-- Table View Tabs -->
          <div class="inline-flex rounded-lg bg-dark-950 p-1 border border-slate-800 text-xs" id="tableTabGroup">
            <button data-tab="sweet" class="px-2.5 py-1 font-bold rounded-md transition bg-emerald-600 text-white">⭐ Sweet Spot</button>
            <button data-tab="all" class="px-2.5 py-1 font-medium rounded-md transition text-slate-400 hover:text-white">Semua</button>
            <button data-tab="premium" class="px-2.5 py-1 font-medium rounded-md transition text-slate-400 hover:text-white">Premium</button>
            <button data-tab="budget" class="px-2.5 py-1 font-medium rounded-md transition text-slate-400 hover:text-white">Budget</button>
            <button data-tab="lagging" class="px-2.5 py-1 font-medium rounded-md transition text-slate-400 hover:text-white">Lagging</button>
          </div>
        </div>
      </div>

      <!-- Table Container -->
      <div class="overflow-x-auto rounded-lg border border-slate-800">
        <table class="w-full text-left text-xs text-slate-300 divide-y divide-slate-800">
          <thead class="bg-slate-900/90 text-slate-400 font-semibold uppercase tracking-wider text-[11px]">
            <tr>
              <th class="px-3 py-2.5 cursor-pointer hover:text-white" data-sort="id">#</th>
              <th class="px-3 py-2.5 cursor-pointer hover:text-white" data-sort="model">Model</th>
              <th class="px-3 py-2.5 cursor-pointer hover:text-white" data-sort="provider">Provider</th>
              <th class="px-3 py-2.5 cursor-pointer hover:text-white" data-sort="thinking">Thinking</th>
              <th class="px-3 py-2.5 cursor-pointer hover:text-white text-right" data-sort="score">Score (Avg)</th>
              <th class="px-3 py-2.5 cursor-pointer hover:text-white text-right" data-sort="cost">Cost/Task ($)</th>
              <th class="px-3 py-2.5 cursor-pointer hover:text-white text-right" data-sort="cost_efficient">Cost Eff.</th>
              <th class="px-3 py-2.5 text-center">Kuadran</th>
              <th class="px-3 py-2.5 text-right cursor-pointer hover:text-white" data-sort="aa_agentic">Agentic</th>
              <th class="px-3 py-2.5 text-right cursor-pointer hover:text-white" data-sort="aa_economics">Econ</th>
              <th class="px-3 py-2.5 text-center">Aksi / Patokan</th>
            </tr>
          </thead>
          <tbody id="tableBody" class="divide-y divide-slate-800/60 bg-dark-900/40">
            <!-- Injected via JS -->
          </tbody>
        </table>
      </div>
    </section>
  </main>

  <footer class="max-w-7xl mx-auto mt-8 pt-4 border-t border-slate-800/80 text-center text-xs text-slate-500">
    <p>AI Trading Agent • LLM Benchmark Analysis Suite • Evaluasi 72 Model LLM Terbobot</p>
  </footer>

  <!-- Application Logic -->
  <script>
    // Embedded Data
    const rawModels = {data_json};
    const datasetStats = {stats_json};

    // Provider Color Palette
    const providerColors = {{
      'Antrhopic': '#f97316',
      'OpenAI': '#10b981',
      'Google': '#3b82f6',
      'XAI': '#e11d48',
      'Meta': '#8b5cf6',
      'Qwen': '#06b6d4',
      'DeepSeek': '#14b8a6',
      'ZAI': '#ec4899',
      'MoonshotAI': '#f59e0b',
      'MiniMax': '#64748b',
      'Xiaomi': '#f43f5e'
    }};

    // State with LocalStorage Recovery
    let savedSettings = null;
    try {{
      savedSettings = JSON.parse(localStorage.getItem('llm_quadrant_thresholds') || 'null');
    }} catch (e) {{}}

    let currentCenterMode = savedSettings ? (savedSettings.mode || 'custom') : 'median';
    let scoreThreshold = savedSettings ? savedSettings.score : datasetStats.score_median;
    let costThreshold = savedSettings ? savedSettings.cost : datasetStats.cost_median;
    let currentScale = 'linear'; // 'linear' | 'log'
    let selectedProviders = new Set(rawModels.map(m => m.provider));
    let selectedThinking = new Set(rawModels.map(m => m.thinking));
    let activeTableTab = 'sweet';
    let searchQuery = '';
    let sortColumn = 'score';
    let sortAsc = false;
    let clickToSetMode = false;

    // DOM Elements
    const chartDom = document.getElementById('quadrantChart');
    const myChart = echarts.init(chartDom, 'dark', {{ renderer: 'canvas' }});
    const numScore = document.getElementById('numScore');
    const rangeScore = document.getElementById('rangeScore');
    const numCost = document.getElementById('numCost');
    const rangeCost = document.getElementById('rangeCost');
    const liveCounterPill = document.getElementById('liveCounterPill');
    const tableBody = document.getElementById('tableBody');
    const searchInput = document.getElementById('searchInput');
    const toast = document.getElementById('toastNotification');
    const toastMessage = document.getElementById('toastMessage');
    const btnToggleClickMode = document.getElementById('btnToggleClickMode');
    const clickModeIndicator = document.getElementById('clickModeIndicator');
    const clickModeText = document.getElementById('clickModeText');
    const clickModeChartBadge = document.getElementById('clickModeChartBadge');

    function showToast(msg) {{
      toastMessage.textContent = msg;
      toast.classList.remove('translate-y-16', 'opacity-0');
      setTimeout(() => {{
        toast.classList.add('translate-y-16', 'opacity-0');
      }}, 2400);
    }}

    function saveState() {{
      try {{
        localStorage.setItem('llm_quadrant_thresholds', JSON.stringify({{
          score: scoreThreshold,
          cost: costThreshold,
          mode: currentCenterMode
        }}));
      }} catch (e) {{}}
    }}

    // Helper: Determine Quadrant for a model
    function getModelQuadrant(m, sThresh = scoreThreshold, cThresh = costThreshold) {{
      const isHighScore = m.score >= sThresh;
      const isLowCost = m.cost <= cThresh;
      if (isHighScore && isLowCost) return 'sweet';
      if (isHighScore && !isLowCost) return 'premium';
      if (!isHighScore && isLowCost) return 'budget';
      return 'lagging';
    }}

    // Master function to set thresholds from any source (slider, input, stepper, preset, click, model)
    function setThresholds(scoreVal, costVal, mode = 'custom', showNotice = false, noticeText = '') {{
      scoreThreshold = Math.max(20.0, Math.min(65.0, parseFloat(scoreVal)));
      costThreshold = Math.max(0.000, Math.min(2.000, parseFloat(costVal)));
      currentCenterMode = mode;

      // Sync form fields
      numScore.value = scoreThreshold.toFixed(2);
      rangeScore.value = scoreThreshold.toFixed(2);
      numCost.value = costThreshold.toFixed(3);
      rangeCost.value = costThreshold.toFixed(3);

      // Update Preset active state
      document.querySelectorAll('.preset-btn').forEach(btn => {{
        if (btn.dataset.preset === mode) {{
          btn.classList.add('bg-emerald-600', 'text-white', 'shadow');
          btn.classList.remove('bg-slate-800', 'text-slate-300');
        }} else {{
          btn.classList.remove('bg-emerald-600', 'text-white', 'shadow');
          btn.classList.add('bg-slate-800', 'text-slate-300');
        }}
      }});

      saveState();
      updateKPIs();
      renderChart();
      renderTable();

      if (showNotice && noticeText) {{
        showToast(noticeText);
      }}
    }}

    // Update KPIs & Live Counter
    function updateKPIs() {{
      const sweetModels = rawModels.filter(m => getModelQuadrant(m) === 'sweet');
      const count = sweetModels.length;
      const pct = ((count / rawModels.length) * 100).toFixed(1);

      document.getElementById('kpiTotalModels').textContent = rawModels.length;
      document.getElementById('kpiSweetSpotCount').textContent = count;
      document.getElementById('kpiSweetSpotPercent').textContent = `(${{pct}}%)`;
      liveCounterPill.textContent = `🎯 ${{count}} model (${{pct}}%) di Sweet Spot`;

      if (count > 0) {{
        const topScore = [...sweetModels].sort((a, b) => b.score - a.score)[0];
        document.getElementById('kpiTopScoreModel').textContent = `${{topScore.model}} (${{topScore.thinking}})`;
        document.getElementById('kpiTopScoreDetail').textContent = `Skor: ${{topScore.score.toFixed(2)}} | Cost: $${{topScore.cost.toFixed(2)}}`;

        const lowestCost = [...sweetModels].sort((a, b) => a.cost - b.cost || b.score - a.score)[0];
        document.getElementById('kpiLowestCostModel').textContent = `${{lowestCost.model}} (${{lowestCost.thinking}})`;
        document.getElementById('kpiLowestCostDetail').textContent = `Cost: $${{lowestCost.cost.toFixed(2)}} | Skor: ${{lowestCost.score.toFixed(2)}}`;
      }} else {{
        document.getElementById('kpiTopScoreModel').textContent = 'Tidak ada';
        document.getElementById('kpiTopScoreDetail').textContent = '-';
        document.getElementById('kpiLowestCostModel').textContent = 'Tidak ada';
        document.getElementById('kpiLowestCostDetail').textContent = '-';
      }}

      let modeText = 'Custom';
      if (currentCenterMode === 'median') modeText = 'Median';
      else if (currentCenterMode === 'mean') modeText = 'Mean';
      else if (currentCenterMode === 'elite') modeText = 'Elite';
      else if (currentCenterMode === 'budget') modeText = 'Budget';
      else if (currentCenterMode === 'balanced') modeText = 'Balanced';
      else if (currentCenterMode === 'model') modeText = 'Model Ref';

      document.getElementById('kpiCenterMode').textContent = modeText;
      document.getElementById('kpiScoreThreshold').textContent = scoreThreshold.toFixed(2);
      document.getElementById('kpiCostThreshold').textContent = `$${{costThreshold.toFixed(4)}}`;
    }}

    // Render ECharts
    function renderChart() {{
      const filtered = rawModels.filter(m => 
        selectedProviders.has(m.provider) && 
        selectedThinking.has(m.thinking)
      );

      const providers = Array.from(new Set(rawModels.map(m => m.provider))).sort();

      const series = providers.map(p => {{
        const pModels = filtered.filter(m => m.provider === p);
        const data = pModels.map(m => {{
          const quad = getModelQuadrant(m);
          return {{
            name: m.model,
            value: [m.cost, m.score, m.cost_efficient, m.thinking, m.provider, quad, m],
            itemStyle: {{
              color: providerColors[p] || '#94a3b8',
              borderColor: quad === 'sweet' ? '#10b981' : '#1e293b',
              borderWidth: quad === 'sweet' ? 2.5 : 1,
              shadowBlur: quad === 'sweet' ? 14 : 0,
              shadowColor: '#10b981'
            }}
          }};
        }});

        return {{
          name: p,
          type: 'scatter',
          symbolSize: function(val) {{
            return val[5] === 'sweet' ? 18 : 13;
          }},
          data: data,
          emphasis: {{
            focus: 'self',
            itemStyle: {{
              borderColor: '#ffffff',
              borderWidth: 2.5,
              shadowBlur: 16,
              shadowColor: 'rgba(255,255,255,0.9)'
            }}
          }}
        }};
      }});

      const maxX = currentScale === 'log' ? 2.0 : 1.9;
      const minX = currentScale === 'log' ? 0.001 : -0.05;

      const markSeries = {{
        name: 'Quadrants',
        type: 'scatter',
        data: [],
        markArea: {{
          silent: true,
          data: [
            // Top-Left: Sweet Spot (High Score, Low Cost) - HIGHLIGHTED!
            [
              {{
                name: '⭐ SWEET SPOT (High Score, Low Cost)',
                itemStyle: {{
                  color: 'rgba(16, 185, 129, 0.13)',
                  borderColor: 'rgba(16, 185, 129, 0.45)',
                  borderWidth: 1.5,
                  borderType: 'solid'
                }},
                label: {{
                  position: ['15%', '10%'],
                  color: '#34d399',
                  fontWeight: 'bold',
                  fontSize: 13,
                  formatter: '⭐ THE SWEET SPOT\\n(Skor Tinggi & Cost Rendah)'
                }},
                coord: [minX, scoreThreshold]
              }},
              {{
                coord: [costThreshold, 62]
              }}
            ],
            // Top-Right: Premium Tier (High Score, High Cost)
            [
              {{
                name: '🚀 PREMIUM (High Score, High Cost)',
                itemStyle: {{
                  color: 'rgba(99, 102, 241, 0.04)'
                }},
                label: {{
                  position: ['70%', '10%'],
                  color: '#818cf8',
                  fontSize: 11,
                  formatter: '🚀 PREMIUM TIER\\n(Skor Tinggi, Biaya Tinggi)'
                }},
                coord: [costThreshold, scoreThreshold]
              }},
              {{
                coord: [maxX, 62]
              }}
            ],
            // Bottom-Left: Budget Utility (Low Score, Low Cost)
            [
              {{
                name: '💡 BUDGET UTILITY (Low Score, Low Cost)',
                itemStyle: {{
                  color: 'rgba(245, 158, 11, 0.04)'
                }},
                label: {{
                  position: ['15%', '85%'],
                  color: '#fbbf24',
                  fontSize: 11,
                  formatter: '💡 BUDGET / HIGH-SPEED'
                }},
                coord: [minX, 18]
              }},
              {{
                coord: [costThreshold, scoreThreshold]
              }}
            ],
            // Bottom-Right: Underperformers (Low Score, High Cost)
            [
              {{
                name: '⚠️ UNDERPERFORMERS (Low Score, High Cost)',
                itemStyle: {{
                  color: 'rgba(239, 68, 68, 0.03)'
                }},
                label: {{
                  position: ['70%', '85%'],
                  color: '#f87171',
                  fontSize: 11,
                  formatter: '⚠️ UNDERPERFORMING'
                }},
                coord: [costThreshold, 18]
              }},
              {{
                coord: [maxX, scoreThreshold]
              }}
            ]
          ]
        }},
        markLine: {{
          silent: true,
          symbol: ['none', 'none'],
          lineStyle: {{
            color: '#f59e0b',
            type: 'dashed',
            width: 1.8
          }},
          data: [
            {{
              xAxis: costThreshold,
              label: {{
                formatter: `Batas Cost: $${{costThreshold.toFixed(3)}}`,
                position: 'end',
                color: '#f59e0b',
                fontSize: 11,
                fontWeight: 'bold',
                backgroundColor: 'rgba(15, 23, 42, 0.85)',
                padding: [3, 6],
                borderRadius: 4
              }}
            }},
            {{
              yAxis: scoreThreshold,
              label: {{
                formatter: `Batas Skor: ${{scoreThreshold.toFixed(2)}}`,
                position: 'end',
                color: '#f59e0b',
                fontSize: 11,
                fontWeight: 'bold',
                backgroundColor: 'rgba(15, 23, 42, 0.85)',
                padding: [3, 6],
                borderRadius: 4
              }}
            }}
          ]
        }}
      }};

      series.push(markSeries);

      const option = {{
        backgroundColor: '#0f172a',
        tooltip: {{
          trigger: 'item',
          backgroundColor: '#1e293b',
          borderColor: '#334155',
          borderWidth: 1,
          textStyle: {{ color: '#f8fafc', fontSize: 12 }},
          formatter: function(params) {{
            if (!params.value || !params.value[6]) return '';
            const m = params.value[6];
            const quad = getModelQuadrant(m);
            let quadBadge = '<span style="color:#10b981;font-weight:bold;">⭐ Sweet Spot (High Score, Low Cost)</span>';
            if (quad === 'premium') quadBadge = '<span style="color:#818cf8;font-weight:bold;">🚀 Premium Tier</span>';
            if (quad === 'budget') quadBadge = '<span style="color:#fbbf24;font-weight:bold;">💡 Budget Utility</span>';
            if (quad === 'lagging') quadBadge = '<span style="color:#f87171;font-weight:bold;">⚠️ Underperforming</span>';

            return `
              <div style="font-family: inherit; min-width: 230px;">
                <div style="font-size: 14px; font-weight: 700; color: #fff; margin-bottom: 2px;">
                  ${{m.model}} <span style="font-size: 11px; font-weight: 400; color: #94a3b8;">(${{m.thinking}})</span>
                </div>
                <div style="font-size: 11px; color: #cbd5e1; margin-bottom: 6px;">Provider: <strong>${{m.provider}}</strong></div>
                <div style="margin-bottom: 8px; font-size: 11px;">${{quadBadge}}</div>
                <div style="border-top: 1px solid #334155; padding-top: 6px; display: grid; grid-template-columns: 1fr 1fr; gap: 4px; font-size: 11px;">
                  <div>Skor Terbobot:</div><div style="text-align: right; font-weight: 700; color: #38bdf8;">${{m.score.toFixed(2)}}</div>
                  <div>Cost / Task:</div><div style="text-align: right; font-weight: 700; color: #facc15;">$${{m.cost.toFixed(2)}}</div>
                  <div>Cost Efficient:</div><div style="text-align: right; font-weight: 700; color: #34d399;">${{m.cost_efficient.toLocaleString()}}</div>
                  <div>Output Tokens:</div><div style="text-align: right; color: #94a3b8;">${{m.tokens.toLocaleString()}}</div>
                </div>
                <div style="border-top: 1px solid #334155; margin-top: 6px; padding-top: 4px; font-size: 10px; color: #94a3b8;">
                  Agentic: <b style="color:#fff">${{m.aa_agentic}}</b> | Econ: <b style="color:#fff">${{m.aa_economics}}</b> | Fin: <b style="color:#fff">${{m.aa_finance}}</b> | Strat: <b style="color:#fff">${{m.aa_strategy}}</b>
                </div>
                <div style="margin-top: 8px; pt-1; text-align: center;">
                  <button onclick="setThresholdsFromModel('${{m.model}}', '${{m.thinking}}')" style="background-color: #059669; color: #ffffff; border: none; padding: 4px 10px; font-size: 10px; font-weight: 700; border-radius: 6px; cursor: pointer;">
                    🎯 Jadikan Model Ini Sebagai Titik Tengah
                  </button>
                </div>
              </div>
            `;
          }}
        }},
        legend: {{
          type: 'scroll',
          top: 10,
          right: 20,
          textStyle: {{ color: '#94a3b8', fontSize: 11 }},
          pageTextStyle: {{ color: '#94a3b8' }}
        }},
        grid: {{
          left: '5%',
          right: '5%',
          bottom: '12%',
          top: '12%',
          containLabel: true
        }},
        xAxis: {{
          type: currentScale === 'log' ? 'log' : 'value',
          name: 'Estimate Cost per Task ($)',
          nameLocation: 'middle',
          nameGap: 30,
          nameTextStyle: {{ color: '#94a3b8', fontWeight: 600, fontSize: 12 }},
          min: currentScale === 'log' ? 0.005 : 0,
          max: 1.85,
          splitLine: {{ lineStyle: {{ color: '#1e293b' }} }},
          axisLabel: {{
            color: '#94a3b8',
            formatter: function(val) {{
              return '$' + val.toFixed(2);
            }}
          }}
        }},
        yAxis: {{
          type: 'value',
          name: 'Weightened Average Score',
          nameLocation: 'middle',
          nameGap: 40,
          nameTextStyle: {{ color: '#94a3b8', fontWeight: 600, fontSize: 12 }},
          min: 20,
          max: 62,
          splitLine: {{ lineStyle: {{ color: '#1e293b' }} }},
          axisLabel: {{ color: '#94a3b8' }}
        }},
        dataZoom: [
          {{
            type: 'inside',
            xAxisIndex: [0],
            yAxisIndex: [0]
          }},
          {{
            type: 'slider',
            show: true,
            xAxisIndex: [0],
            bottom: 5,
            height: 18,
            borderColor: '#334155',
            fillerColor: 'rgba(16, 185, 129, 0.15)',
            textStyle: {{ color: '#64748b', fontSize: 10 }}
          }}
        ],
        series: series
      }};

      myChart.setOption(option, true);
    }}

    // Render Table
    function renderTable() {{
      const query = searchQuery.toLowerCase().trim();
      let list = rawModels.filter(m => {{
        const matchProvider = selectedProviders.has(m.provider);
        const matchThinking = selectedThinking.has(m.thinking);
        const matchSearch = query === '' || 
          m.model.toLowerCase().includes(query) || 
          m.provider.toLowerCase().includes(query);
        return matchProvider && matchThinking && matchSearch;
      }});

      if (activeTableTab !== 'all') {{
        list = list.filter(m => getModelQuadrant(m) === activeTableTab);
      }}

      list.sort((a, b) => {{
        let vA = a[sortColumn];
        let vB = b[sortColumn];
        if (typeof vA === 'string') {{
          vA = vA.toLowerCase();
          vB = vB.toLowerCase();
        }}
        if (vA < vB) return sortAsc ? -1 : 1;
        if (vA > vB) return sortAsc ? 1 : -1;
        return 0;
      }});

      document.getElementById('tableFilteredCount').textContent = `${{list.length}} model ditampilkan`;

      if (list.length === 0) {{
        tableBody.innerHTML = `
          <tr>
            <td colspan="11" class="px-4 py-8 text-center text-slate-500 italic">
              Tidak ada model yang cocok dengan filter dan threshold aktif.
            </td>
          </tr>
        `;
        return;
      }}

      tableBody.innerHTML = list.map(m => {{
        const quad = getModelQuadrant(m);
        let quadBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">⭐ Sweet Spot</span>';
        if (quad === 'premium') quadBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">🚀 Premium</span>';
        if (quad === 'budget') quadBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-amber-500/20 text-amber-300 border border-amber-500/30">💡 Budget</span>';
        if (quad === 'lagging') quadBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-medium bg-rose-500/20 text-rose-300 border border-rose-500/30">⚠️ Lagging</span>';

        const rowBg = quad === 'sweet' ? 'bg-emerald-950/20 hover:bg-emerald-900/30' : 'hover:bg-slate-800/40';

        return `
          <tr class="${{rowBg}} transition cursor-pointer" onclick="focusChartModel('${{m.model}}', '${{m.thinking}}')">
            <td class="px-3 py-2 text-slate-500">${{m.id}}</td>
            <td class="px-3 py-2 font-bold text-white flex items-center gap-1.5">
              <span class="w-2 h-2 rounded-full" style="background-color: ${{providerColors[m.provider] || '#94a3b8'}}"></span>
              ${{m.model}}
            </td>
            <td class="px-3 py-2 text-slate-400">${{m.provider}}</td>
            <td class="px-3 py-2 text-slate-400">${{m.thinking}}</td>
            <td class="px-3 py-2 text-right font-extrabold text-sky-400">${{m.score.toFixed(2)}}</td>
            <td class="px-3 py-2 text-right font-bold text-amber-300">$${{m.cost.toFixed(2)}}</td>
            <td class="px-3 py-2 text-right text-emerald-400 font-mono">${{m.cost_efficient.toLocaleString('id-ID', {{maximumFractionDigits: 1}})}}</td>
            <td class="px-3 py-2 text-center">${{quadBadge}}</td>
            <td class="px-3 py-2 text-right font-mono">${{m.aa_agentic}}</td>
            <td class="px-3 py-2 text-right font-mono">${{m.aa_economics}}</td>
            <td class="px-3 py-2 text-center flex items-center justify-center gap-1.5">
              <button onclick="event.stopPropagation(); focusChartModel('${{m.model}}', '${{m.thinking}}')" class="text-[11px] text-sky-400 hover:text-sky-300 font-medium underline">
                Lihat
              </button>
              <span class="text-slate-600">|</span>
              <button onclick="event.stopPropagation(); setThresholdsFromModel('${{m.model}}', '${{m.thinking}}')" class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 font-semibold" title="Jadikan nilai model ini sebagai titik tengah threshold">
                🎯 Patokan
              </button>
            </td>
          </tr>
        `;
      }}).join('');
    }}

    // Focus model on chart
    window.focusChartModel = function(modelName, thinking) {{
      const found = rawModels.find(m => m.model === modelName && m.thinking === thinking);
      if (!found) return;

      myChart.dispatchAction({{
        type: 'highlight',
        seriesName: found.provider,
        name: found.model
      }});

      myChart.dispatchAction({{
        type: 'showTip',
        dataIndex: 0,
        name: found.model
      }});

      chartDom.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
    }};

    // Set thresholds directly from selected model
    window.setThresholdsFromModel = function(modelName, thinking) {{
      const found = rawModels.find(m => m.model === modelName && m.thinking === thinking);
      if (!found) return;

      setThresholds(
        found.score, 
        found.cost, 
        'model', 
        true, 
        `Patokan disetel ke ${{found.model}}: Skor ${{found.score.toFixed(2)}}, Cost $${{found.cost.toFixed(2)}}`
      );
    }};

    // Setup Stepper buttons & Numeric Inputs
    function initNumericInputsAndSteppers() {{
      // Number input for Score
      numScore.addEventListener('change', (e) => {{
        const val = parseFloat(e.target.value);
        if (!isNaN(val)) setThresholds(val, costThreshold, 'custom');
      }});

      // Range slider for Score
      rangeScore.addEventListener('input', (e) => {{
        setThresholds(e.target.value, costThreshold, 'custom');
      }});

      // Steppers for Score
      document.querySelectorAll('[data-step-score]').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const delta = parseFloat(btn.dataset.stepScore);
          setThresholds(scoreThreshold + delta, costThreshold, 'custom');
        }});
      }});

      // Number input for Cost
      numCost.addEventListener('change', (e) => {{
        const val = parseFloat(e.target.value);
        if (!isNaN(val)) setThresholds(scoreThreshold, val, 'custom');
      }});

      // Range slider for Cost
      rangeCost.addEventListener('input', (e) => {{
        setThresholds(scoreThreshold, e.target.value, 'custom');
      }});

      // Steppers for Cost
      document.querySelectorAll('[data-step-cost]').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const delta = parseFloat(btn.dataset.stepCost);
          setThresholds(scoreThreshold, costThreshold + delta, 'custom');
        }});
      }});

      // Quick Strategy Presets
      document.querySelectorAll('.preset-btn').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const preset = btn.dataset.preset;
          if (preset === 'median') {{
            setThresholds(datasetStats.score_median, datasetStats.cost_median, 'median', true, 'Preset Median diterapkan (50/50 balance)');
          }} else if (preset === 'mean') {{
            setThresholds(datasetStats.score_mean, datasetStats.cost_mean, 'mean', true, 'Preset Mean (Rata-rata) diterapkan');
          }} else if (preset === 'elite') {{
            setThresholds(50.00, 0.150, 'elite', true, 'Preset Elite Value (Skor ≥ 50, Biaya ≤ $0.15) diterapkan');
          }} else if (preset === 'budget') {{
            setThresholds(45.00, 0.050, 'budget', true, 'Preset Ultra Budget (Skor ≥ 45, Biaya ≤ $0.05) diterapkan');
          }} else if (preset === 'balanced') {{
            setThresholds(46.00, 0.100, 'balanced', true, 'Preset Balanced (Skor ≥ 46, Biaya ≤ $0.10) diterapkan');
          }}
        }});
      }});
    }}

    // Setup Click-on-Chart Feature
    function initClickOnChart() {{
      btnToggleClickMode.addEventListener('click', () => {{
        clickToSetMode = !clickToSetMode;
        if (clickToSetMode) {{
          clickModeIndicator.classList.replace('bg-slate-500', 'bg-emerald-400');
          clickModeIndicator.classList.add('animate-pulse');
          clickModeText.textContent = 'ON (Aktif)';
          clickModeText.classList.add('text-emerald-400');
          clickModeChartBadge.classList.remove('hidden');
          chartDom.style.cursor = 'crosshair';
          showToast('Mode Klik Aktif: Klik posisi mana saja di grafik untuk memindahkan garis titik tengah.');
        }} else {{
          clickModeIndicator.classList.replace('bg-emerald-400', 'bg-slate-500');
          clickModeIndicator.classList.remove('animate-pulse');
          clickModeText.textContent = 'OFF';
          clickModeText.classList.remove('text-emerald-400');
          clickModeChartBadge.classList.add('hidden');
          chartDom.style.cursor = 'default';
        }}
      }});

      myChart.getZr().on('click', function(params) {{
        if (!clickToSetMode) return;
        const pointInGrid = myChart.convertFromPixel({{ gridIndex: 0 }}, [params.offsetX, params.offsetY]);
        if (pointInGrid && pointInGrid.length >= 2) {{
          let costVal = Math.max(0, parseFloat(pointInGrid[0].toFixed(3)));
          let scoreVal = Math.max(20, Math.min(62, parseFloat(pointInGrid[1].toFixed(2))));
          setThresholds(
            scoreVal, 
            costVal, 
            'custom', 
            true, 
            `Titik tengah dipindah ke: Skor ${{scoreVal.toFixed(2)}}, Cost $${{costVal.toFixed(3)}}`
          );
        }}
      }});
    }}

    // Setup Filters UI
    function initFiltersUI() {{
      const providers = Array.from(new Set(rawModels.map(m => m.provider))).sort();
      const pContainer = document.getElementById('providerFilterContainer');
      pContainer.innerHTML = '<span class="font-semibold text-slate-400 mr-1">Provider:</span>' + 
        providers.map(p => `
          <button data-provider="${{p}}" class="provider-pill px-2 py-0.5 rounded text-[11px] font-medium border border-slate-700 bg-slate-800 text-slate-200 hover:border-slate-500 transition flex items-center gap-1">
            <span class="w-1.5 h-1.5 rounded-full" style="background-color: ${{providerColors[p] || '#fff'}}"></span>
            ${{p}}
          </button>
        `).join('');

      pContainer.querySelectorAll('.provider-pill').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const prov = btn.dataset.provider;
          if (selectedProviders.has(prov)) {{
            if (selectedProviders.size > 1) {{
              selectedProviders.delete(prov);
              btn.classList.replace('bg-slate-800', 'bg-transparent');
              btn.classList.add('opacity-40');
            }}
          }} else {{
            selectedProviders.add(prov);
            btn.classList.replace('bg-transparent', 'bg-slate-800');
            btn.classList.remove('opacity-40');
          }}
          renderChart();
          renderTable();
        }});
      }});

      // Thinking levels
      const thinkings = ['max', 'xhigh', 'high', 'medium', 'low'];
      const tContainer = document.getElementById('thinkingFilterContainer');
      tContainer.innerHTML = '<span class="font-semibold text-slate-400 mr-1">Thinking:</span>' +
        thinkings.map(t => `
          <button data-thinking="${{t}}" class="thinking-pill px-2 py-0.5 rounded text-[11px] font-medium border border-slate-700 bg-slate-800 text-slate-200 hover:border-slate-500 transition">
            ${{t}}
          </button>
        `).join('');

      tContainer.querySelectorAll('.thinking-pill').forEach(btn => {{
        btn.addEventListener('click', () => {{
          const th = btn.dataset.thinking;
          if (selectedThinking.has(th)) {{
            if (selectedThinking.size > 1) {{
              selectedThinking.delete(th);
              btn.classList.replace('bg-slate-800', 'bg-transparent');
              btn.classList.add('opacity-40');
            }}
          }} else {{
            selectedThinking.add(th);
            btn.classList.replace('bg-transparent', 'bg-slate-800');
            btn.classList.remove('opacity-40');
          }}
          renderChart();
          renderTable();
        }});
      }});
    }}

    // Setup Scale Toggle
    function initScaleControls() {{
      const scaleGroup = document.getElementById('scaleGroup');
      const buttons = scaleGroup.querySelectorAll('button');
      buttons.forEach(btn => {{
        btn.addEventListener('click', () => {{
          buttons.forEach(b => {{
            b.classList.remove('bg-slate-700', 'text-white');
            b.classList.add('text-slate-400');
          }});
          btn.classList.add('bg-slate-700', 'text-white');
          btn.classList.remove('text-slate-400');

          currentScale = btn.dataset.scale;
          renderChart();
        }});
      }});
    }}

    // Setup Table Tabs
    function initTableTabs() {{
      const tabGroup = document.getElementById('tableTabGroup');
      const buttons = tabGroup.querySelectorAll('button');
      buttons.forEach(btn => {{
        btn.addEventListener('click', () => {{
          buttons.forEach(b => {{
            b.classList.remove('bg-emerald-600', 'text-white', 'font-bold');
            b.classList.add('text-slate-400', 'font-medium');
          }});
          btn.classList.add('bg-emerald-600', 'text-white', 'font-bold');
          btn.classList.remove('text-slate-400', 'font-medium');

          activeTableTab = btn.dataset.tab;
          renderTable();
        }});
      }});
    }}

    // Setup Table Sorting
    function initTableSorting() {{
      document.querySelectorAll('th[data-sort]').forEach(th => {{
        th.addEventListener('click', () => {{
          const col = th.dataset.sort;
          if (sortColumn === col) {{
            sortAsc = !sortAsc;
          }} else {{
            sortColumn = col;
            sortAsc = (col === 'model' || col === 'provider' || col === 'thinking');
          }}
          renderTable();
        }});
      }});
    }}

    // Export PNG
    document.getElementById('btnExportPng').addEventListener('click', () => {{
      const url = myChart.getDataURL({{
        type: 'png',
        pixelRatio: 2,
        backgroundColor: '#090d16'
      }});
      const a = document.createElement('a');
      a.download = `llm_quadrant_analysis_score_${{scoreThreshold.toFixed(1)}}_cost_${{costThreshold.toFixed(2)}}.png`;
      a.href = url;
      a.click();
    }});

    // Export CSV
    document.getElementById('btnExportCsv').addEventListener('click', () => {{
      const headers = ['ID', 'Provider', 'Model', 'Thinking Level', 'Weighted Average', 'Estimate Cost ($)', 'Cost Efficient', 'Quadrant', 'AA-Agentic', 'AA-Economics', 'AA-Strategy', 'AA-Finance'];
      const rows = rawModels.map(m => [
        m.id,
        `"${{m.provider}}"`,
        `"${{m.model}}"`,
        `"${{m.thinking}}"`,
        m.score,
        m.cost,
        m.cost_efficient,
        getModelQuadrant(m),
        m.aa_agentic,
        m.aa_economics,
        m.aa_strategy,
        m.aa_finance
      ]);

      const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map(e => e.join(','))].join('\\n');
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement('a');
      link.setAttribute('href', encodedUri);
      link.setAttribute('download', `llm_models_quadrant_score_${{scoreThreshold.toFixed(1)}}_cost_${{costThreshold.toFixed(2)}}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }});

    // Search Input
    searchInput.addEventListener('input', (e) => {{
      searchQuery = e.target.value;
      renderTable();
    }});

    // Reset Default Filters & Thresholds
    document.getElementById('btnResetFilters').addEventListener('click', () => {{
      selectedProviders = new Set(rawModels.map(m => m.provider));
      selectedThinking = new Set(rawModels.map(m => m.thinking));
      currentScale = 'linear';
      searchQuery = '';
      searchInput.value = '';
      activeTableTab = 'sweet';

      try {{
        localStorage.removeItem('llm_quadrant_thresholds');
      }} catch (e) {{}}

      document.querySelectorAll('.provider-pill').forEach(btn => {{
        btn.classList.replace('bg-transparent', 'bg-slate-800');
        btn.classList.remove('opacity-40');
      }});
      document.querySelectorAll('.thinking-pill').forEach(btn => {{
        btn.classList.replace('bg-transparent', 'bg-slate-800');
        btn.classList.remove('opacity-40');
      }});

      setThresholds(datasetStats.score_median, datasetStats.cost_median, 'median', true, 'Filter dan threshold dikembalikan ke default Median.');
    }});

    // Window Resize
    window.addEventListener('resize', () => {{
      myChart.resize();
    }});

    // Initialization
    initFiltersUI();
    initNumericInputsAndSteppers();
    initClickOnChart();
    initScaleControls();
    initTableTabs();
    initTableSorting();
    
    // Apply initial thresholds
    setThresholds(scoreThreshold, costThreshold, currentCenterMode);
  </script>
</body>
</html>
"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    print(f"Successfully generated quadrant visualization: {output_path}")


def main():
    root_dir = Path(__file__).resolve().parent.parent
    csv_path = root_dir / "model_all.csv"
    output_path = root_dir / "model_quadrant_analysis.html"

    if not csv_path.exists():
        print(f"Error: CSV file not found at {csv_path}")
        return

    print(f"Reading data from: {csv_path}")
    models = parse_csv(str(csv_path))
    stats = compute_stats(models)
    
    print(f"Parsed {len(models)} models.")
    print(f"Stats: Median Score={stats['score_median']}, Median Cost=${stats['cost_median']:.4f}")
    print(f"Stats: Mean Score={stats['score_mean']}, Mean Cost=${stats['cost_mean']:.4f}")
    
    generate_html(models, stats, str(output_path))


if __name__ == "__main__":
    main()
