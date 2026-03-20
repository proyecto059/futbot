pub fn env_flag_enabled(name: &str) -> bool {
    match std::env::var(name) {
        Ok(v) => matches!(
            v.trim().to_ascii_lowercase().as_str(),
            "1" | "true" | "yes" | "on"
        ),
        Err(_) => false,
    }
}

pub fn mismatch_ratio(lhs: &[u8], rhs: &[u8]) -> f64 {
    let n = lhs.len().min(rhs.len());
    if n == 0 {
        return 0.0;
    }

    let mismatch = lhs
        .iter()
        .zip(rhs.iter())
        .take(n)
        .filter(|(a, b)| a != b)
        .count();
    mismatch as f64 / n as f64
}

pub fn env_f64(name: &str, default: f64) -> f64 {
    std::env::var(name)
        .ok()
        .and_then(|v| v.trim().parse::<f64>().ok())
        .filter(|v| v.is_finite() && *v >= 0.0)
        .unwrap_or(default)
}
