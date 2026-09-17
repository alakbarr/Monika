import math

def compress_tool_payload(
    data,
    strip_empty_collections: bool = True,
    preserve_keys: tuple = (
        "events", "news", "bars", "trades", "positions",
        "dxy", "vix", "fedwatch", "treasury_yields", "interest_rates",
        "cot_signals", "economic_calendar", "news_digest", "surprise_summary",
        "eurusd_momentum", "market_session", "funding_rate", "fear_greed"
    )
):
    """
    Mengompresi payload JSON secara rekursif untuk mengurangi penggunaan token LLM:
    1. Menghapus key dengan value None atau string kosong "".
    2. Menghapus empty collections ([], {}) kecuali jika key berada dalam preserve_keys.
    3. Membulatkan nilai float berlebih menjadi maksimal 5 desimal.
    """
    if isinstance(data, dict):
        compressed_dict = {}
        for k, v in data.items():
            if v is None or v == "":
                continue
            if strip_empty_collections and v in ([], {}) and k not in preserve_keys:
                continue
            
            compressed_val = compress_tool_payload(v, strip_empty_collections=strip_empty_collections, preserve_keys=preserve_keys)
            if compressed_val is not None and compressed_val != "":
                if not strip_empty_collections or compressed_val not in ([], {}) or k in preserve_keys:
                    compressed_dict[k] = compressed_val
                
        return compressed_dict

    elif isinstance(data, list):
        compressed_list = []
        for item in data:
            compressed_val = compress_tool_payload(item, strip_empty_collections=strip_empty_collections, preserve_keys=preserve_keys)
            if compressed_val is not None and compressed_val != "":
                if not strip_empty_collections or compressed_val not in ([], {}):
                    compressed_list.append(compressed_val)
        return compressed_list

    elif isinstance(data, float):
        # Jika nilai float sangat dekat dengan 0 (<= 1e-9), kembalikan 0
        if math.isclose(data, 0.0, abs_tol=1e-9) or abs(data) <= 1e-9:
            return 0.0
        # Presisi adaptif: untuk angka sangat kecil (< 0.001), pertahankan hingga 6 significant figures
        if abs(data) < 0.001:
            rounded = float(f"{data:.6g}")
        else:
            rounded = round(data, 5)
        # Jika setelah dibulatkan hasilnya integer, jadikan int
        if isinstance(rounded, float) and rounded.is_integer():
            return int(rounded)
        return rounded

    return data
