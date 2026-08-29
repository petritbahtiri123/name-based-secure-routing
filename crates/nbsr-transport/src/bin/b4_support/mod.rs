#[derive(Clone, Copy, Debug, PartialEq)]
pub(crate) struct MixedAdmissionConfig {
    pub(crate) rate_per_second: f64,
    pub(crate) scheduled: u64,
}

pub(crate) fn mixed_admission_config(
    rate_per_second: Option<f64>,
    duration_seconds: Option<f64>,
) -> Result<MixedAdmissionConfig, &'static str> {
    let rate = rate_per_second.unwrap_or(0.0);
    if !rate.is_finite() || rate < 0.0 {
        return Err("mixed admission rate must be finite and non-negative");
    }
    if rate == 0.0 {
        return Ok(MixedAdmissionConfig {
            rate_per_second: 0.0,
            scheduled: 0,
        });
    }
    let duration = duration_seconds.ok_or("mixed admissions require duration-based measurement")?;
    if !duration.is_finite() || duration <= 0.0 {
        return Err("mixed duration must be finite and positive");
    }
    let scheduled = (rate * duration).round() as u64;
    if !(1..=8_000).contains(&scheduled) {
        return Err("mixed admission count must be in 1..=8000");
    }
    Ok(MixedAdmissionConfig {
        rate_per_second: rate,
        scheduled,
    })
}

pub(crate) fn percentile(values: &[u64], p: f64) -> Option<u64> {
    if values.is_empty() {
        return None;
    }
    Some(values[((values.len() - 1) as f64 * p).round() as usize])
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mixed_config_derives_bounded_fixed_admission_count() {
        assert_eq!(
            mixed_admission_config(Some(25.0), Some(10.0)).unwrap(),
            MixedAdmissionConfig {
                rate_per_second: 25.0,
                scheduled: 250,
            }
        );
        assert_eq!(
            mixed_admission_config(Some(0.0), Some(10.0)).unwrap(),
            MixedAdmissionConfig {
                rate_per_second: 0.0,
                scheduled: 0,
            }
        );
        assert_eq!(
            mixed_admission_config(Some(0.25), Some(2.0))
                .unwrap()
                .scheduled,
            1
        );
    }

    #[test]
    fn mixed_config_rejects_unbounded_or_non_duration_runs() {
        assert!(mixed_admission_config(Some(1.0), None).is_err());
        assert!(mixed_admission_config(Some(-1.0), Some(10.0)).is_err());
        assert!(mixed_admission_config(Some(1_000.0), Some(10.0)).is_err());
    }

    #[test]
    fn percentile_is_absent_without_admissions() {
        assert_eq!(percentile(&[], 0.99), None);
        assert_eq!(percentile(&[10, 20, 30], 0.50), Some(20));
    }
}
