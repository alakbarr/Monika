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
