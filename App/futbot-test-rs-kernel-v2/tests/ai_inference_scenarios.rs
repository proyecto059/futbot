#[path = "../src/config.rs"]
mod config;

#[path = "../src/ai_inference.rs"]
mod ai_inference;

use ai_inference::{AIInferenceThread, should_log_ai_error};
use ai_inference::{parse_output_layout, parse_row_conf_class, AIOutputFormat};

#[test]
fn ai_thread_reports_no_latest_result_in_stub_mode() {
    let ai = AIInferenceThread::new();
    assert!(ai.get_latest_result().is_none());
}

#[test]
fn ai_error_log_policy_matches_expected_rate_limit() {
    assert!(should_log_ai_error(1));
    assert!(should_log_ai_error(5));
    assert!(!should_log_ai_error(6));
    assert!(should_log_ai_error(50));
    assert!(!should_log_ai_error(51));
}

#[test]
fn parse_layout_accepts_nx6_rank3() {
    let (rows, stride, format) =
        parse_output_layout(&[1, 300, 6]).expect("layout should parse");
    assert_eq!(rows, 300);
    assert_eq!(stride, 6);
    assert_eq!(format, AIOutputFormat::Nx6);
}

#[test]
fn parse_layout_accepts_nx7_rank3() {
    let (rows, stride, format) =
        parse_output_layout(&[1, 300, 7]).expect("layout should parse");
    assert_eq!(rows, 300);
    assert_eq!(stride, 7);
    assert_eq!(format, AIOutputFormat::Nx7);
}

#[test]
fn parse_layout_accepts_nx6_rank2() {
    let (rows, stride, format) = parse_output_layout(&[300, 6]).expect("layout should parse");
    assert_eq!(rows, 300);
    assert_eq!(stride, 6);
    assert_eq!(format, AIOutputFormat::Nx6);
}

#[test]
fn parse_layout_accepts_nx7_rank2() {
    let (rows, stride, format) = parse_output_layout(&[300, 7]).expect("layout should parse");
    assert_eq!(rows, 300);
    assert_eq!(stride, 7);
    assert_eq!(format, AIOutputFormat::Nx7);
}

#[test]
fn parse_layout_rejects_unsupported_last_dim() {
    let err = parse_output_layout(&[1, 300, 84]).expect_err("layout should fail");
    assert!(err.to_string().contains("6 or 7"));
}

#[test]
fn parse_row_conf_class_supports_nx6() {
    let row = [10.0, 20.0, 30.0, 40.0, 0.61, 0.0];
    let (conf, class_id) = parse_row_conf_class(&row, 0, AIOutputFormat::Nx6);
    assert!((conf - 0.61).abs() < f32::EPSILON);
    assert!((class_id - 0.0).abs() < f32::EPSILON);
}

#[test]
fn parse_row_conf_class_supports_nx7() {
    let row = [10.0, 20.0, 30.0, 40.0, 0.80, 0.50, 0.0];
    let (conf, class_id) = parse_row_conf_class(&row, 0, AIOutputFormat::Nx7);
    assert!((conf - 0.40).abs() < 1e-6);
    assert!((class_id - 0.0).abs() < f32::EPSILON);
}

#[cfg(feature = "ai")]
#[test]
fn fill_tensor_from_rgb_writes_nchw_channels() -> anyhow::Result<()> {
    use ai_inference::fill_tensor_from_rgb;
    use ndarray::Array4;
    use opencv::{
        core::{self, Mat, Scalar, Vec3b},
        prelude::*,
    };

    fn approx_eq(a: f32, b: f32) -> bool {
        (a - b).abs() < 1e-6
    }

    let mut rgb = Mat::new_rows_cols_with_default(2, 2, core::CV_8UC3, Scalar::all(0.0))?;

    *rgb.at_2d_mut::<Vec3b>(0, 0)? = Vec3b::from([10, 20, 30]);
    *rgb.at_2d_mut::<Vec3b>(0, 1)? = Vec3b::from([40, 50, 60]);
    *rgb.at_2d_mut::<Vec3b>(1, 0)? = Vec3b::from([70, 80, 90]);
    *rgb.at_2d_mut::<Vec3b>(1, 1)? = Vec3b::from([100, 110, 120]);

    let mut tensor = Array4::<f32>::zeros((1, 3, 2, 2));
    fill_tensor_from_rgb(&rgb, &mut tensor)?;

    assert!(approx_eq(tensor[[0, 0, 0, 0]], 10.0 / 255.0));
    assert!(approx_eq(tensor[[0, 0, 0, 1]], 40.0 / 255.0));
    assert!(approx_eq(tensor[[0, 0, 1, 0]], 70.0 / 255.0));
    assert!(approx_eq(tensor[[0, 0, 1, 1]], 100.0 / 255.0));

    assert!(approx_eq(tensor[[0, 1, 0, 0]], 20.0 / 255.0));
    assert!(approx_eq(tensor[[0, 1, 0, 1]], 50.0 / 255.0));
    assert!(approx_eq(tensor[[0, 1, 1, 0]], 80.0 / 255.0));
    assert!(approx_eq(tensor[[0, 1, 1, 1]], 110.0 / 255.0));

    assert!(approx_eq(tensor[[0, 2, 0, 0]], 30.0 / 255.0));
    assert!(approx_eq(tensor[[0, 2, 0, 1]], 60.0 / 255.0));
    assert!(approx_eq(tensor[[0, 2, 1, 0]], 90.0 / 255.0));
    assert!(approx_eq(tensor[[0, 2, 1, 1]], 120.0 / 255.0));

    Ok(())
}
