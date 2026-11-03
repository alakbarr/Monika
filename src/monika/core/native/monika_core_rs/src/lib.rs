use std::slice;

#[no_mangle]
pub extern "C" fn monika_vpin_fractional_f64(
    prices_ptr: *const f64,
    volumes_ptr: *const f64,
    len: usize,
    bucket_volume: f64,
    n_buckets: usize,
) -> f64 {
    if prices_ptr.is_null() || volumes_ptr.is_null() || len < 2 || bucket_volume <= 0.0 || !bucket_volume.is_finite() {
        return f64::NAN;
    }
    let prices = unsafe { slice::from_raw_parts(prices_ptr, len) };
    let volumes = unsafe { slice::from_raw_parts(volumes_ptr, len) };

    let mut bucket_buys: Vec<f64> = Vec::with_capacity(n_buckets.max(64));
    let mut bucket_sells: Vec<f64> = Vec::with_capacity(n_buckets.max(64));

    let mut curr_b = 0.0_f64;
    let mut curr_s = 0.0_f64;
    let mut rem_space = bucket_volume;

    for i in 0..len {
        let tot_v = volumes[i];
        if !(tot_v > 0.0) || !tot_v.is_finite() || !prices[i].is_finite() {
            continue;
        }
        let dp = if i == 0 { 0.0 } else { prices[i] - prices[i - 1] };
        let buy_pct = if dp > 0.0 {
            1.0
        } else if dp < 0.0 {
            0.0
        } else {
            0.5
        };
        let mut b_left = tot_v * buy_pct;
        let mut s_left = tot_v * (1.0 - buy_pct);
        let mut v_left = tot_v;

        while v_left >= rem_space {
            let frac = rem_space / v_left;
            curr_b += b_left * frac;
            curr_s += s_left * frac;
            bucket_buys.push(curr_b);
            bucket_sells.push(curr_s);

            b_left -= b_left * frac;
            s_left -= s_left * frac;
            v_left -= rem_space;

            curr_b = 0.0;
            curr_s = 0.0;
            rem_space = bucket_volume;
        }

        if v_left > 0.0 {
            curr_b += b_left;
            curr_s += s_left;
            rem_space -= v_left;
        }
    }

    let min_req = if n_buckets < 10 { n_buckets } else { 10 };
    if bucket_buys.len() < min_req {
        return 0.5;
    }

    let start = bucket_buys.len().saturating_sub(n_buckets);
    let mut sum_imb = 0.0_f64;
    let mut denom = 0.0_f64;
    for idx in start..bucket_buys.len() {
        let b = bucket_buys[idx];
        let s = bucket_sells[idx];
        sum_imb += (b - s).abs();
        denom += b + s;
    }

    if denom <= 1e-12 {
        return 0.5;
    }
    (sum_imb / denom).clamp(0.0, 1.0)
}

#[no_mangle]
pub extern "C" fn monika_kyle_lambda_ols_f64(
    y_ptr: *const f64,
    x_ptr: *const f64,
    len: usize,
    window: usize,
    out_ptr: *mut f64,
) -> i32 {
    if y_ptr.is_null() || x_ptr.is_null() || out_ptr.is_null() || len < window || window < 3 {
        return -1;
    }
    let y = unsafe { slice::from_raw_parts(y_ptr, len) };
    let x = unsafe { slice::from_raw_parts(x_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(window - 1) {
        out[i] = 0.0;
    }

    let w_f = window as f64;
    for i in (window - 1)..len {
        let start = i + 1 - window;
        let y_sl = &y[start..=i];
        let x_sl = &x[start..=i];

        let mut x_sum = 0.0_f64;
        let mut y_sum = 0.0_f64;
        for k in 0..window {
            x_sum += x_sl[k];
            y_sum += y_sl[k];
        }
        let x_mean = x_sum / w_f;
        let y_mean = y_sum / w_f;

        let mut denom = 0.0_f64;
        let mut num = 0.0_f64;
        for k in 0..window {
            let x_dm = x_sl[k] - x_mean;
            let y_dm = y_sl[k] - y_mean;
            denom += x_dm * x_dm;
            num += x_dm * y_dm;
        }
        if denom < 1e-12 || !denom.is_finite() || !num.is_finite() {
            out[i] = 0.0;
        } else {
            out[i] = num / denom;
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_tick_rule_cvd_f64(
    prices_ptr: *const f64,
    volumes_ptr: *const f64,
    len: usize,
    out_cvd_ptr: *mut f64,
) -> i32 {
    if prices_ptr.is_null() || volumes_ptr.is_null() || out_cvd_ptr.is_null() || len == 0 {
        return -1;
    }
    let prices = unsafe { slice::from_raw_parts(prices_ptr, len) };
    let volumes = unsafe { slice::from_raw_parts(volumes_ptr, len) };
    let out_cvd = unsafe { slice::from_raw_parts_mut(out_cvd_ptr, len) };

    let mut cvd = 0.0_f64;
    let mut prev_dir = 1.0_f64;
    for i in 0..len {
        let p = prices[i];
        let vol = volumes[i];
        let dir = if i == 0 {
            1.0
        } else if p > prices[i - 1] {
            1.0
        } else if p < prices[i - 1] {
            -1.0
        } else {
            prev_dir
        };
        prev_dir = dir;
        cvd += dir * vol;
        out_cvd[i] = cvd;
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_find_swings_f64(
    highs_ptr: *const f64,
    lows_ptr: *const f64,
    len: usize,
    window: usize,
    out_high_mask: *mut u8,
    out_low_mask: *mut u8,
) -> i32 {
    if highs_ptr.is_null() || lows_ptr.is_null() || out_high_mask.is_null() || out_low_mask.is_null() {
        return -1;
    }
    let n = window.max(1);
    let highs = unsafe { slice::from_raw_parts(highs_ptr, len) };
    let lows = unsafe { slice::from_raw_parts(lows_ptr, len) };
    let h_mask = unsafe { slice::from_raw_parts_mut(out_high_mask, len) };
    let l_mask = unsafe { slice::from_raw_parts_mut(out_low_mask, len) };

    for i in 0..len {
        h_mask[i] = 0;
        l_mask[i] = 0;
    }
    if len < 2 * n + 1 {
        return 0;
    }

    for i in n..(len - n) {
        if highs[i] <= highs[i - 1] && lows[i] >= lows[i - 1] {
            continue;
        }
        let h_val = highs[i];
        let l_val = lows[i];

        let mut is_sh = true;
        for k in (i - n)..i {
            if highs[k] >= h_val {
                is_sh = false;
                break;
            }
        }
        if is_sh {
            for k in (i + 1)..=(i + n) {
                if highs[k] >= h_val {
                    is_sh = false;
                    break;
                }
            }
        }
        if is_sh {
            h_mask[i] = 1;
        }

        let mut is_sl = true;
        for k in (i - n)..i {
            if lows[k] <= l_val {
                is_sl = false;
                break;
            }
        }
        if is_sl {
            for k in (i + 1)..=(i + n) {
                if lows[k] <= l_val {
                    is_sl = false;
                    break;
                }
            }
        }
        if is_sl {
            l_mask[i] = 1;
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_find_swing_pivots_f64(
    highs_ptr: *const f64,
    lows_ptr: *const f64,
    len: usize,
    order: usize,
    out_indices: *mut usize,
    out_types: *mut u8,
    out_prices: *mut f64,
) -> isize {
    if highs_ptr.is_null() || lows_ptr.is_null() || out_indices.is_null() || out_types.is_null() || out_prices.is_null() {
        return -1;
    }
    let ord = order.max(1);
    if len <= 2 * ord {
        return 0;
    }
    let highs = unsafe { slice::from_raw_parts(highs_ptr, len) };
    let lows = unsafe { slice::from_raw_parts(lows_ptr, len) };
    let indices = unsafe { slice::from_raw_parts_mut(out_indices, len) };
    let types = unsafe { slice::from_raw_parts_mut(out_types, len) };
    let prices = unsafe { slice::from_raw_parts_mut(out_prices, len) };

    let mut count: usize = 0;

    for i in ord..(len - ord) {
        let h_i = highs[i];
        let mut is_peak = true;
        for k in 1..=ord {
            if h_i < highs[i - k] || h_i < highs[i + k] {
                is_peak = false;
                break;
            }
        }
        let mut p_type: u8 = 0;
        let mut p_price: f64 = 0.0;
        if is_peak {
            p_type = 1; // high
            p_price = h_i;
        } else {
            let l_i = lows[i];
            let mut is_trough = true;
            for k in 1..=ord {
                if l_i > lows[i - k] || l_i > lows[i + k] {
                    is_trough = false;
                    break;
                }
            }
            if is_trough {
                p_type = 2; // low
                p_price = l_i;
            }
        }

        if p_type != 0 {
            if count == 0 {
                indices[0] = i;
                types[0] = p_type;
                prices[0] = p_price;
                count = 1;
            } else {
                let last_idx = count - 1;
                if types[last_idx] == p_type {
                    if (p_type == 1 && p_price > prices[last_idx])
                        || (p_type == 2 && p_price < prices[last_idx])
                    {
                        indices[last_idx] = i;
                        prices[last_idx] = p_price;
                    }
                } else {
                    indices[count] = i;
                    types[count] = p_type;
                    prices[count] = p_price;
                    count += 1;
                }
            }
        }
    }
    count as isize
}

#[no_mangle]
pub extern "C" fn monika_eval_equity_paths_f64(
    sampled_matrix_ptr: *const f64,
    num_simulations: usize,
    n_trades: usize,
    initial_equity: f64,
    ruin_drawdown_pct: f64,
    out_max_dds_ptr: *mut f64,
    out_final_eqs_ptr: *mut f64,
    out_ruin_count_ptr: *mut usize,
) -> i32 {
    if sampled_matrix_ptr.is_null()
        || out_max_dds_ptr.is_null()
        || out_final_eqs_ptr.is_null()
        || out_ruin_count_ptr.is_null()
        || num_simulations == 0
        || n_trades == 0
    {
        return -1;
    }
    let mat = unsafe { slice::from_raw_parts(sampled_matrix_ptr, num_simulations * n_trades) };
    let out_max_dds = unsafe { slice::from_raw_parts_mut(out_max_dds_ptr, num_simulations) };
    let out_final_eqs = unsafe { slice::from_raw_parts_mut(out_final_eqs_ptr, num_simulations) };

    let ruin_barrier = initial_equity * (1.0 - ruin_drawdown_pct);
    let mut ruin_count: usize = 0;

    for sim in 0..num_simulations {
        let row = &mat[sim * n_trades..(sim + 1) * n_trades];
        let mut eq = initial_equity;
        let mut running_max = initial_equity;
        let mut max_dd = 0.0_f64;
        let mut min_eq = initial_equity;

        for &r in row {
            let mult = (1.0 + r).max(0.0);
            eq *= mult;
            if eq > running_max {
                running_max = eq;
            }
            if eq < min_eq {
                min_eq = eq;
            }
            if running_max > 0.0 {
                let dd = (running_max - eq) / running_max;
                if dd > max_dd {
                    max_dd = dd;
                }
            }
        }

        out_final_eqs[sim] = eq;
        out_max_dds[sim] = max_dd * 100.0;
        if max_dd >= ruin_drawdown_pct || min_eq < ruin_barrier {
            ruin_count += 1;
        }
    }

    unsafe {
        *out_ruin_count_ptr = ruin_count;
    }
    0
}

struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    #[inline]
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }
    #[inline]
    fn next_u64(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9e3779b97f4a7c15);
        let mut z = self.state;
        z = (z ^ (z >> 30)).wrapping_mul(0xbf58476d1ce4e5b9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94d049bb133111eb);
        z ^ (z >> 31)
    }
    #[inline]
    fn next_usize(&mut self, bound: usize) -> usize {
        (self.next_u64() as usize) % bound
    }
}

#[no_mangle]
pub extern "C" fn monika_monte_carlo_simulate_f64(
    returns_ptr: *const f64,
    n_trades: usize,
    num_simulations: usize,
    initial_equity: f64,
    ruin_drawdown_pct: f64,
    mode_code: u32,
    block_size: usize,
    seed: u64,
    out_max_dds_ptr: *mut f64,
    out_final_eqs_ptr: *mut f64,
    out_ruin_count_ptr: *mut usize,
) -> i32 {
    if returns_ptr.is_null()
        || out_max_dds_ptr.is_null()
        || out_final_eqs_ptr.is_null()
        || out_ruin_count_ptr.is_null()
        || n_trades == 0
        || num_simulations == 0
    {
        return -1;
    }
    let returns = unsafe { slice::from_raw_parts(returns_ptr, n_trades) };
    let out_max_dds = unsafe { slice::from_raw_parts_mut(out_max_dds_ptr, num_simulations) };
    let out_final_eqs = unsafe { slice::from_raw_parts_mut(out_final_eqs_ptr, num_simulations) };

    let mut rng = SplitMix64::new(seed ^ 0xA5A5_5A5A_F0F0_0F0F);
    let mut buf = returns.to_vec();
    let ruin_barrier = initial_equity * (1.0 - ruin_drawdown_pct);
    let mut ruin_count: usize = 0;
    let b_size = block_size.max(2);

    for sim in 0..num_simulations {
        let mut eq = initial_equity;
        let mut running_max = initial_equity;
        let mut max_dd = 0.0_f64;
        let mut min_eq = initial_equity;

        if mode_code == 0 {
            // Permutation (Fisher-Yates in-place shuffle)
            for i in (1..n_trades).rev() {
                let j = rng.next_usize(i + 1);
                buf.swap(i, j);
            }
            for &r in &buf {
                let mult = (1.0 + r).max(0.0);
                eq *= mult;
                if eq > running_max {
                    running_max = eq;
                }
                if eq < min_eq {
                    min_eq = eq;
                }
                if running_max > 0.0 {
                    let dd = (running_max - eq) / running_max;
                    if dd > max_dd {
                        max_dd = dd;
                    }
                }
            }
        } else if mode_code == 1 {
            // Bootstrap with replacement
            for _ in 0..n_trades {
                let r = returns[rng.next_usize(n_trades)];
                let mult = (1.0 + r).max(0.0);
                eq *= mult;
                if eq > running_max {
                    running_max = eq;
                }
                if eq < min_eq {
                    min_eq = eq;
                }
                if running_max > 0.0 {
                    let dd = (running_max - eq) / running_max;
                    if dd > max_dd {
                        max_dd = dd;
                    }
                }
            }
        } else {
            // Circular Block Bootstrap
            let mut generated = 0usize;
            while generated < n_trades {
                let start_idx = rng.next_usize(n_trades);
                for b in 0..b_size {
                    if generated >= n_trades {
                        break;
                    }
                    let r = returns[(start_idx + b) % n_trades];
                    let mult = (1.0 + r).max(0.0);
                    eq *= mult;
                    if eq > running_max {
                        running_max = eq;
                    }
                    if eq < min_eq {
                        min_eq = eq;
                    }
                    if running_max > 0.0 {
                        let dd = (running_max - eq) / running_max;
                        if dd > max_dd {
                            max_dd = dd;
                        }
                    }
                    generated += 1;
                }
            }
        }

        out_final_eqs[sim] = eq;
        out_max_dds[sim] = max_dd * 100.0;
        if max_dd >= ruin_drawdown_pct || min_eq < ruin_barrier {
            ruin_count += 1;
        }
    }

    unsafe {
        *out_ruin_count_ptr = ruin_count;
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_cscv_pbo_from_chunks_f64(
    chunk_sums_ptr: *const f64,
    chunk_sq_sums_ptr: *const f64,
    chunk_counts_ptr: *const usize,
    n_partitions: usize,
    n_strats: usize,
    is_combos_ptr: *const usize,
    n_combos: usize,
    half_s: usize,
    out_oos_ranks_ptr: *mut f64,
) -> isize {
    if chunk_sums_ptr.is_null()
        || chunk_sq_sums_ptr.is_null()
        || chunk_counts_ptr.is_null()
        || is_combos_ptr.is_null()
        || out_oos_ranks_ptr.is_null()
    {
        return -1;
    }
    let chunk_sums = unsafe { slice::from_raw_parts(chunk_sums_ptr, n_partitions * n_strats) };
    let chunk_sq_sums = unsafe { slice::from_raw_parts(chunk_sq_sums_ptr, n_partitions * n_strats) };
    let chunk_counts = unsafe { slice::from_raw_parts(chunk_counts_ptr, n_partitions) };
    let is_combos = unsafe { slice::from_raw_parts(is_combos_ptr, n_combos * half_s) };
    let out_ranks = unsafe { slice::from_raw_parts_mut(out_oos_ranks_ptr, n_combos) };

    // Precompute total sums across all partitions per strategy
    let mut tot_sums = vec![0.0_f64; n_strats];
    let mut tot_sq_sums = vec![0.0_f64; n_strats];
    let mut tot_count: usize = 0;
    for c in 0..n_partitions {
        tot_count += chunk_counts[c];
        let base = c * n_strats;
        for j in 0..n_strats {
            tot_sums[j] += chunk_sums[base + j];
            tot_sq_sums[j] += chunk_sq_sums[base + j];
        }
    }

    let mut is_sum = vec![0.0_f64; n_strats];
    let mut is_sq = vec![0.0_f64; n_strats];
    let mut oos_sr = vec![f64::NEG_INFINITY; n_strats];
    let mut underperforming: isize = 0;

    for combo_idx in 0..n_combos {
        is_sum.fill(0.0);
        is_sq.fill(0.0);
        let mut is_n: usize = 0;
        let combo_slice = &is_combos[combo_idx * half_s..(combo_idx + 1) * half_s];
        for &c_idx in combo_slice {
            is_n += chunk_counts[c_idx];
            let base = c_idx * n_strats;
            for j in 0..n_strats {
                is_sum[j] += chunk_sums[base + j];
                is_sq[j] += chunk_sq_sums[base + j];
            }
        }
        let oos_n = tot_count - is_n;
        let is_nf = is_n as f64;
        let oos_nf = oos_n as f64;

        let mut best_is_strat: usize = 0;
        let mut best_is_sr = f64::NEG_INFINITY;

        for j in 0..n_strats {
            let mean_is = is_sum[j] / is_nf;
            let var_is = ((is_sq[j] - (is_sum[j] * mean_is)) / (is_nf - 1.0)).max(0.0);
            let std_is = var_is.sqrt();
            let sr_is = if std_is > 1e-12 { mean_is / std_is } else { f64::NEG_INFINITY };
            if sr_is > best_is_sr {
                best_is_sr = sr_is;
                best_is_strat = j;
            }

            let sum_oos = tot_sums[j] - is_sum[j];
            let sq_oos = tot_sq_sums[j] - is_sq[j];
            let mean_oos = sum_oos / oos_nf;
            let var_oos = ((sq_oos - (sum_oos * mean_oos)) / (oos_nf - 1.0)).max(0.0);
            let std_oos = var_oos.sqrt();
            oos_sr[j] = if std_oos > 1e-12 { mean_oos / std_oos } else { f64::NEG_INFINITY };
        }

        let target_oos = oos_sr[best_is_strat];
        let mut valid_count = 0usize;
        let mut le_count = 0usize;
        for &val in &oos_sr {
            if val.is_finite() {
                valid_count += 1;
                if val <= target_oos {
                    le_count += 1;
                }
            }
        }
        let rank = if valid_count > 0 {
            (le_count as f64) / (valid_count as f64)
        } else {
            0.5
        };
        out_ranks[combo_idx] = rank;
        if rank <= 0.50 {
            underperforming += 1;
        }
    }

    underperforming
}

#[no_mangle]
pub extern "C" fn monika_ts_rank_f64(
    arr_ptr: *const f64,
    len: usize,
    window: usize,
    out_ptr: *mut f64,
) -> i32 {
    if arr_ptr.is_null() || out_ptr.is_null() || len < window || window == 0 {
        return -1;
    }
    let arr = unsafe { slice::from_raw_parts(arr_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(window - 1) {
        out[i] = f64::NAN;
    }

    let w_f = window as f64;
    for t in (window - 1)..len {
        let win_start = t + 1 - window;
        let last = arr[t];
        if !last.is_finite() {
            out[t] = f64::NAN;
            continue;
        }

        let mut has_nan = false;
        let mut count_less = 0usize;
        let mut count_eq = 0usize;

        for i in win_start..=t {
            let v = arr[i];
            if !v.is_finite() {
                has_nan = true;
                break;
            }
            if v < last {
                count_less += 1;
            } else if v == last {
                count_eq += 1;
            }
        }

        if has_nan {
            out[t] = f64::NAN;
        } else {
            out[t] = (count_less as f64 + 0.5 * (count_eq as f64 + 1.0)) / w_f;
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_decay_linear_f64(
    arr_ptr: *const f64,
    len: usize,
    window: usize,
    out_ptr: *mut f64,
) -> i32 {
    if arr_ptr.is_null() || out_ptr.is_null() || len < window || window == 0 {
        return -1;
    }
    let arr = unsafe { slice::from_raw_parts(arr_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(window - 1) {
        out[i] = f64::NAN;
    }

    let sum_w = (window * (window + 1) / 2) as f64;

    for t in (window - 1)..len {
        let win_start = t + 1 - window;
        let mut has_nan = false;
        let mut weighted_sum = 0.0_f64;

        for k in 0..window {
            let v = arr[win_start + k];
            if !v.is_finite() {
                has_nan = true;
                break;
            }
            let w = (k + 1) as f64;
            weighted_sum += v * w;
        }

        if has_nan {
            out[t] = f64::NAN;
        } else {
            out[t] = weighted_sum / sum_w;
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_rolling_corr_f64(
    x_ptr: *const f64,
    y_ptr: *const f64,
    len: usize,
    window: usize,
    out_ptr: *mut f64,
) -> i32 {
    if x_ptr.is_null() || y_ptr.is_null() || out_ptr.is_null() || len < window || window < 2 {
        return -1;
    }
    let x = unsafe { slice::from_raw_parts(x_ptr, len) };
    let y = unsafe { slice::from_raw_parts(y_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(window - 1) {
        out[i] = f64::NAN;
    }

    let w_f = window as f64;
    let denom_deg = (window - 1) as f64;

    for t in (window - 1)..len {
        let win_start = t + 1 - window;
        let mut has_nan = false;
        let mut sum_x = 0.0_f64;
        let mut sum_y = 0.0_f64;

        for i in win_start..=t {
            let xi = x[i];
            let yi = y[i];
            if !xi.is_finite() || !yi.is_finite() {
                has_nan = true;
                break;
            }
            sum_x += xi;
            sum_y += yi;
        }

        if has_nan {
            out[t] = f64::NAN;
            continue;
        }

        let mean_x = sum_x / w_f;
        let mean_y = sum_y / w_f;

        let mut var_x = 0.0_f64;
        let mut var_y = 0.0_f64;
        let mut cov_xy = 0.0_f64;

        for i in win_start..=t {
            let dx = x[i] - mean_x;
            let dy = y[i] - mean_y;
            var_x += dx * dx;
            var_y += dy * dy;
            cov_xy += dx * dy;
        }

        let var_x_sample = var_x / denom_deg;
        let var_y_sample = var_y / denom_deg;

        if var_x_sample <= 1e-14 || var_y_sample <= 1e-14 {
            out[t] = f64::NAN;
        } else {
            let std_prod = (var_x_sample * var_y_sample).sqrt();
            let cov_sample = cov_xy / denom_deg;
            let corr = (cov_sample / std_prod).clamp(-1.0, 1.0);
            out[t] = corr;
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_sma_f64(
    arr_ptr: *const f64,
    len: usize,
    period: usize,
    out_ptr: *mut f64,
) -> i32 {
    if arr_ptr.is_null() || out_ptr.is_null() || len < period || period == 0 {
        return -1;
    }
    let arr = unsafe { slice::from_raw_parts(arr_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(period - 1) {
        out[i] = f64::NAN;
    }

    let p_f = period as f64;
    let mut sum = 0.0_f64;
    for i in 0..period {
        sum += arr[i];
    }
    out[period - 1] = sum / p_f;

    for i in period..len {
        sum += arr[i] - arr[i - period];
        out[i] = sum / p_f;
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_ema_f64(
    arr_ptr: *const f64,
    len: usize,
    period: usize,
    out_ptr: *mut f64,
) -> i32 {
    if arr_ptr.is_null() || out_ptr.is_null() || len < period || period == 0 {
        return -1;
    }
    let arr = unsafe { slice::from_raw_parts(arr_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(period - 1) {
        out[i] = f64::NAN;
    }

    let alpha = 2.0_f64 / (period as f64 + 1.0_f64);
    let mut curr = arr[0];

    for t in 1..(period - 1) {
        curr = alpha * arr[t] + (1.0_f64 - alpha) * curr;
    }

    for t in (period - 1)..len {
        curr = alpha * arr[t] + (1.0_f64 - alpha) * curr;
        out[t] = curr;
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_rsi_f64(
    arr_ptr: *const f64,
    len: usize,
    period: usize,
    out_ptr: *mut f64,
) -> i32 {
    if arr_ptr.is_null() || out_ptr.is_null() || len < period || period == 0 {
        return -1;
    }
    let arr = unsafe { slice::from_raw_parts(arr_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(period - 1) {
        out[i] = f64::NAN;
    }

    let alpha = 1.0_f64 / (period as f64);
    let mut curr_up = 0.0_f64;
    let mut curr_dn = 0.0_f64;

    for t in 1..len {
        let diff = arr[t] - arr[t - 1];
        let up = if diff > 0.0 { diff } else { 0.0 };
        let dn = if diff < 0.0 { -diff } else { 0.0 };
        curr_up = alpha * up + (1.0_f64 - alpha) * curr_up;
        curr_dn = alpha * dn + (1.0_f64 - alpha) * curr_dn;

        if t >= period - 1 {
            if curr_dn == 0.0 {
                out[t] = 100.0;
            } else {
                let rs = curr_up / curr_dn;
                out[t] = 100.0 - (100.0 / (1.0 + rs));
            }
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_atr_f64(
    highs_ptr: *const f64,
    lows_ptr: *const f64,
    closes_ptr: *const f64,
    len: usize,
    period: usize,
    out_ptr: *mut f64,
) -> i32 {
    if highs_ptr.is_null() || lows_ptr.is_null() || closes_ptr.is_null() || out_ptr.is_null() || len < period || period == 0 {
        return -1;
    }
    let highs = unsafe { slice::from_raw_parts(highs_ptr, len) };
    let lows = unsafe { slice::from_raw_parts(lows_ptr, len) };
    let closes = unsafe { slice::from_raw_parts(closes_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(period - 1) {
        out[i] = 0.0;
    }

    let mut tr_sum = 0.0_f64;
    let mut prev_atr = 0.0_f64;
    let p_f = period as f64;

    for i in 0..len {
        let h = highs[i];
        let l = lows[i];
        let tr = if i == 0 {
            h - l
        } else {
            let cp = closes[i - 1];
            (h - l).max((h - cp).abs()).max((l - cp).abs())
        };

        if i < period {
            tr_sum += tr;
            if i == period - 1 {
                prev_atr = tr_sum / p_f;
                out[i] = prev_atr;
            }
        } else {
            prev_atr = (prev_atr * (p_f - 1.0) + tr) / p_f;
            out[i] = prev_atr;
        }
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_bollinger_bands_f64(
    arr_ptr: *const f64,
    len: usize,
    period: usize,
    num_std: f64,
    out_mid_ptr: *mut f64,
    out_upper_ptr: *mut f64,
    out_lower_ptr: *mut f64,
) -> i32 {
    if arr_ptr.is_null() || out_mid_ptr.is_null() || out_upper_ptr.is_null() || out_lower_ptr.is_null() || len < period || period == 0 {
        return -1;
    }
    let arr = unsafe { slice::from_raw_parts(arr_ptr, len) };
    let out_mid = unsafe { slice::from_raw_parts_mut(out_mid_ptr, len) };
    let out_upper = unsafe { slice::from_raw_parts_mut(out_upper_ptr, len) };
    let out_lower = unsafe { slice::from_raw_parts_mut(out_lower_ptr, len) };

    for i in 0..(period - 1) {
        out_mid[i] = f64::NAN;
        out_upper[i] = f64::NAN;
        out_lower[i] = f64::NAN;
    }

    let p_f = period as f64;

    for i in (period - 1)..len {
        let start = i + 1 - period;
        let mut sum = 0.0_f64;
        let mut sq_sum = 0.0_f64;
        for k in start..=i {
            let v = arr[k];
            sum += v;
            sq_sum += v * v;
        }
        let mean = sum / p_f;
        let var = ((sq_sum / p_f) - (mean * mean)).max(0.0);
        let std = var.sqrt();

        out_mid[i] = mean;
        out_upper[i] = mean + num_std * std;
        out_lower[i] = mean - num_std * std;
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_find_fvg_f64(
    highs_ptr: *const f64,
    lows_ptr: *const f64,
    atr_ptr: *const f64,
    len: usize,
    min_atr_factor: f64,
    out_indices_ptr: *mut usize,
    out_types_ptr: *mut u8,
    out_gap_high_ptr: *mut f64,
    out_gap_low_ptr: *mut f64,
    out_filled_idx_ptr: *mut isize,
) -> isize {
    if highs_ptr.is_null()
        || lows_ptr.is_null()
        || atr_ptr.is_null()
        || out_indices_ptr.is_null()
        || out_types_ptr.is_null()
        || out_gap_high_ptr.is_null()
        || out_gap_low_ptr.is_null()
        || out_filled_idx_ptr.is_null()
        || len < 3
    {
        return -1;
    }
    let highs = unsafe { slice::from_raw_parts(highs_ptr, len) };
    let lows = unsafe { slice::from_raw_parts(lows_ptr, len) };
    let atr = unsafe { slice::from_raw_parts(atr_ptr, len) };

    let out_indices = unsafe { slice::from_raw_parts_mut(out_indices_ptr, len) };
    let out_types = unsafe { slice::from_raw_parts_mut(out_types_ptr, len) };
    let out_gap_high = unsafe { slice::from_raw_parts_mut(out_gap_high_ptr, len) };
    let out_gap_low = unsafe { slice::from_raw_parts_mut(out_gap_low_ptr, len) };
    let out_filled_idx = unsafe { slice::from_raw_parts_mut(out_filled_idx_ptr, len) };

    let mut count = 0usize;

    for i in 0..(len - 2) {
        let c1_h = highs[i];
        let c1_l = lows[i];
        let c3_h = highs[i + 2];
        let c3_l = lows[i + 2];
        let current_atr = atr[i + 2];

        // Bullish FVG: candle_3_low > candle_1_high
        if c3_l > c1_h {
            let gap_low = c1_h;
            let gap_high = c3_l;
            let gap_size = gap_high - gap_low;

            if gap_size >= current_atr * min_atr_factor {
                let gap_mid = (gap_high + gap_low) / 2.0;
                let mut filled: isize = -1;
                for j in (i + 3)..len {
                    if lows[j] <= gap_mid {
                        filled = j as isize;
                        break;
                    }
                }
                out_indices[count] = i + 2;
                out_types[count] = 1; // 1 = bullish
                out_gap_high[count] = gap_high;
                out_gap_low[count] = gap_low;
                out_filled_idx[count] = filled;
                count += 1;
            }
        } else if c3_h < c1_l {
            // Bearish FVG: candle_3_high < candle_1_low
            let gap_high = c1_l;
            let gap_low = c3_h;
            let gap_size = gap_high - gap_low;

            if gap_size >= current_atr * min_atr_factor {
                let gap_mid = (gap_high + gap_low) / 2.0;
                let mut filled: isize = -1;
                for j in (i + 3)..len {
                    if highs[j] >= gap_mid {
                        filled = j as isize;
                        break;
                    }
                }
                out_indices[count] = i + 2;
                out_types[count] = 2; // 2 = bearish
                out_gap_high[count] = gap_high;
                out_gap_low[count] = gap_low;
                out_filled_idx[count] = filled;
                count += 1;
            }
        }
    }

    count as isize
}

#[no_mangle]
pub extern "C" fn monika_yang_zhang_f64(
    opens_ptr: *const f64,
    highs_ptr: *const f64,
    lows_ptr: *const f64,
    closes_ptr: *const f64,
    len: usize,
    window: usize,
    out_ptr: *mut f64,
) -> i32 {
    if opens_ptr.is_null()
        || highs_ptr.is_null()
        || lows_ptr.is_null()
        || closes_ptr.is_null()
        || out_ptr.is_null()
        || len < window + 1
        || window < 2
    {
        return -1;
    }
    let opens = unsafe { slice::from_raw_parts(opens_ptr, len) };
    let highs = unsafe { slice::from_raw_parts(highs_ptr, len) };
    let lows = unsafe { slice::from_raw_parts(lows_ptr, len) };
    let closes = unsafe { slice::from_raw_parts(closes_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..len {
        out[i] = f64::NAN;
    }

    let n = window;
    let n_f = n as f64;
    let k = 0.34 / (1.34 + ((n_f + 1.0) / (n_f - 1.0)));

    let mut log_oc = vec![0.0_f64; len];
    let mut log_co = vec![0.0_f64; len];
    let mut rs_term = vec![0.0_f64; len];

    for i in 0..len {
        let op = opens[i].max(1e-6);
        let hp = highs[i].max(op);
        let lp = lows[i].max(1e-6);
        let cp = closes[i].max(1e-6);

        log_oc[i] = (cp / (op + 1e-12)).ln();

        if i > 0 {
            let cp_prev = closes[i - 1].max(1e-6);
            log_co[i] = (op / (cp_prev + 1e-12)).ln();
        }

        let lho = (hp / (op + 1e-12)).ln();
        let llo = (lp / (op + 1e-12)).ln();
        let lhc = (hp / (cp + 1e-12)).ln();
        let llc = (lp / (cp + 1e-12)).ln();
        rs_term[i] = lho * lhc + llo * llc;
    }

    for i in n..len {
        let mut rs_sum = 0.0_f64;
        let mut co_sum = 0.0_f64;
        let mut oc_sum = 0.0_f64;
        for j in (i - n + 1)..=i {
            rs_sum += rs_term[j];
            co_sum += log_co[j];
            oc_sum += log_oc[j];
        }
        let rs_mean = rs_sum / n_f;
        let co_mean = co_sum / n_f;
        let oc_mean = oc_sum / n_f;

        let mut co_var_sum = 0.0_f64;
        let mut oc_var_sum = 0.0_f64;
        for j in (i - n + 1)..=i {
            let d_co = log_co[j] - co_mean;
            co_var_sum += d_co * d_co;
            let d_oc = log_oc[j] - oc_mean;
            oc_var_sum += d_oc * d_oc;
        }
        let co_var = co_var_sum / (n_f - 1.0);
        let oc_var = oc_var_sum / (n_f - 1.0);

        let yz_var = co_var + (oc_var * k) + (rs_mean * (1.0 - k));
        out[i] = if yz_var > 0.0 { yz_var.sqrt() } else { 0.0 };
    }

    0
}

#[no_mangle]
pub extern "C" fn monika_stochastic_f64(
    highs_ptr: *const f64,
    lows_ptr: *const f64,
    closes_ptr: *const f64,
    len: usize,
    k_period: usize,
    d_period: usize,
    out_k_ptr: *mut f64,
    out_d_ptr: *mut f64,
) -> i32 {
    if highs_ptr.is_null()
        || lows_ptr.is_null()
        || closes_ptr.is_null()
        || out_k_ptr.is_null()
        || out_d_ptr.is_null()
        || len < k_period
        || k_period == 0
        || d_period == 0
    {
        return -1;
    }
    let highs = unsafe { slice::from_raw_parts(highs_ptr, len) };
    let lows = unsafe { slice::from_raw_parts(lows_ptr, len) };
    let closes = unsafe { slice::from_raw_parts(closes_ptr, len) };
    let out_k = unsafe { slice::from_raw_parts_mut(out_k_ptr, len) };
    let out_d = unsafe { slice::from_raw_parts_mut(out_d_ptr, len) };

    for i in 0..len {
        out_k[i] = f64::NAN;
        out_d[i] = f64::NAN;
    }

    for i in (k_period - 1)..len {
        let mut min_l = f64::INFINITY;
        let mut max_h = f64::NEG_INFINITY;
        for j in (i - k_period + 1)..=i {
            if lows[j] < min_l {
                min_l = lows[j];
            }
            if highs[j] > max_h {
                max_h = highs[j];
            }
        }
        let diff = max_h - min_l;
        out_k[i] = if diff.abs() > 1e-12 {
            100.0 * (closes[i] - min_l) / diff
        } else {
            50.0
        };
    }

    let min_d_idx = k_period - 1 + d_period - 1;
    if len > min_d_idx {
        for i in min_d_idx..len {
            let mut sum_k = 0.0_f64;
            for j in (i - d_period + 1)..=i {
                sum_k += out_k[j];
            }
            out_d[i] = sum_k / (d_period as f64);
        }
    }

    0
}

#[no_mangle]
pub extern "C" fn monika_macd_f64(
    closes_ptr: *const f64,
    len: usize,
    fast_period: usize,
    slow_period: usize,
    signal_period: usize,
    out_macd_ptr: *mut f64,
    out_signal_ptr: *mut f64,
    out_hist_ptr: *mut f64,
) -> i32 {
    if closes_ptr.is_null()
        || out_macd_ptr.is_null()
        || out_signal_ptr.is_null()
        || out_hist_ptr.is_null()
        || len < slow_period
        || fast_period == 0
        || slow_period <= fast_period
        || signal_period == 0
    {
        return -1;
    }
    let closes = unsafe { slice::from_raw_parts(closes_ptr, len) };
    let out_macd = unsafe { slice::from_raw_parts_mut(out_macd_ptr, len) };
    let out_signal = unsafe { slice::from_raw_parts_mut(out_signal_ptr, len) };
    let out_hist = unsafe { slice::from_raw_parts_mut(out_hist_ptr, len) };

    for i in 0..len {
        out_macd[i] = f64::NAN;
        out_signal[i] = f64::NAN;
        out_hist[i] = f64::NAN;
    }

    let fast_alpha = 2.0_f64 / (fast_period as f64 + 1.0_f64);
    let slow_alpha = 2.0_f64 / (slow_period as f64 + 1.0_f64);
    let signal_alpha = 2.0_f64 / (signal_period as f64 + 1.0_f64);

    let mut fast_curr = closes[0];
    let mut slow_curr = closes[0];

    let mut fast_ema = vec![f64::NAN; len];

    for t in 1..(fast_period - 1) {
        fast_curr = fast_alpha * closes[t] + (1.0_f64 - fast_alpha) * fast_curr;
    }
    for t in (fast_period - 1)..len {
        fast_curr = fast_alpha * closes[t] + (1.0_f64 - fast_alpha) * fast_curr;
        fast_ema[t] = fast_curr;
    }

    for t in 1..(slow_period - 1) {
        slow_curr = slow_alpha * closes[t] + (1.0_f64 - slow_alpha) * slow_curr;
    }
    for t in (slow_period - 1)..len {
        slow_curr = slow_alpha * closes[t] + (1.0_f64 - slow_alpha) * slow_curr;
        out_macd[t] = fast_ema[t] - slow_curr;
    }

    let t0 = slow_period - 1;
    let mut sig_curr = out_macd[t0];

    for t in (t0 + 1)..(t0 + signal_period - 1) {
        if t < len {
            sig_curr = signal_alpha * out_macd[t] + (1.0_f64 - signal_alpha) * sig_curr;
        }
    }

    let sig_start = t0 + signal_period - 1;
    for t in sig_start..len {
        sig_curr = signal_alpha * out_macd[t] + (1.0_f64 - signal_alpha) * sig_curr;
        out_signal[t] = sig_curr;
        out_hist[t] = out_macd[t] - sig_curr;
    }

    0
}

#[no_mangle]
pub extern "C" fn monika_ts_argmax_f64(
    arr_ptr: *const f64,
    len: usize,
    window: usize,
    out_ptr: *mut f64,
) -> i32 {
    if arr_ptr.is_null() || out_ptr.is_null() || len < window || window < 1 {
        return -1;
    }
    let arr = unsafe { slice::from_raw_parts(arr_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(window - 1) {
        out[i] = f64::NAN;
    }

    for i in (window - 1)..len {
        let start = i - window + 1;
        let mut max_val = f64::NEG_INFINITY;
        let mut max_idx = 0usize;
        let mut has_nan = false;

        for offset in 0..window {
            let v = arr[start + offset];
            if v.is_nan() {
                has_nan = true;
                break;
            }
            if v > max_val {
                max_val = v;
                max_idx = offset;
            }
        }
        out[i] = if has_nan { f64::NAN } else { max_idx as f64 };
    }
    0
}

#[no_mangle]
pub extern "C" fn monika_ts_argmin_f64(
    arr_ptr: *const f64,
    len: usize,
    window: usize,
    out_ptr: *mut f64,
) -> i32 {
    if arr_ptr.is_null() || out_ptr.is_null() || len < window || window < 1 {
        return -1;
    }
    let arr = unsafe { slice::from_raw_parts(arr_ptr, len) };
    let out = unsafe { slice::from_raw_parts_mut(out_ptr, len) };

    for i in 0..(window - 1) {
        out[i] = f64::NAN;
    }

    for i in (window - 1)..len {
        let start = i - window + 1;
        let mut min_val = f64::INFINITY;
        let mut min_idx = 0usize;
        let mut has_nan = false;

        for offset in 0..window {
            let v = arr[start + offset];
            if v.is_nan() {
                has_nan = true;
                break;
            }
            if v < min_val {
                min_val = v;
                min_idx = offset;
            }
        }
        out[i] = if has_nan { f64::NAN } else { min_idx as f64 };
    }
    0
}
