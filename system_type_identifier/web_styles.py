APP_CSS = r"""
:root {
  --bg: #081116;
  --surface: #0d191f;
  --panel: #111e24;
  --panel-2: #0d2b23;
  --border: #29404a;
  --muted: #8faab5;
  --text: #f4f7f6;
  --green: #65d5a7;
  --lime: #6fc926;
  --red: #ff776f;
  --amber: #f5b85b;
}
body, .q-page { background: var(--bg); color: var(--text); font-family: Inter, "Segoe UI", sans-serif; }
.nicegui-content { padding: 0 !important; }
.app-shell { min-height: 100vh; background: var(--bg); }
.topbar { height: 74px; padding: 0 30px; background: var(--surface); border-bottom: 1px solid var(--border); }
.logo-mark { width: 40px; height: 40px; border-radius: 10px; background: #153b30; color: var(--lime); font-size: 22px; font-weight: 800; }
.brand-title { color: #fff; font-size: 16px; font-weight: 700; line-height: 1.1; }
.brand-sub { color: var(--muted); font-size: 11px; }
.statusbar { min-height: 38px; padding: 0 28px; background: var(--surface); border-top: 1px solid var(--border); color: var(--muted); font-size: 11px; }
.page-wrap { width: min(1060px, calc(100vw - 56px)); margin: 0 auto; padding: 42px 0 36px; }
.eyebrow { color: #55b993; font-size: 11px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }
.page-title { color: #f7faf8; font-size: 36px; font-weight: 400; letter-spacing: -.035em; line-height: 1.15; }
.subtitle, .muted { color: var(--muted); font-size: 14px; }
.field-label { color: #e5efec; font-size: 12px; font-weight: 650; line-height: 1.35; }
.control-group { gap: 8px; }
.panel, .amat-card { width: 100%; background: var(--panel); border: 1px solid var(--border); border-radius: 14px; box-shadow: none; }
.login-card { width: min(960px, calc(100vw - 48px)); min-height: 530px; border: 1px solid var(--border); border-radius: 15px; overflow: hidden; }
.login-feature { min-height: 530px; padding: 52px 58px; background: var(--panel-2); }
.login-form { min-height: 530px; padding: 50px 58px 46px; background: #111c22; }
.hero { color: #f7faf8; font-size: 44px; font-weight: 400; letter-spacing: -.04em; line-height: 1.04; }
.hero-accent { color: var(--lime); }
.delta-input .q-field__control, .delta-select .q-field__control, .amat-input .q-field__control {
  min-height: 54px; padding: 0 16px; background: #09151a; border-radius: 9px; color: white;
}
.delta-input .q-field__native, .delta-select .q-field__native, .delta-select .q-field__input,
.amat-input .q-field__native, .amat-input input { color: #f5f8f7 !important; }
.delta-input .q-field__label, .delta-select .q-field__label, .amat-input .q-field__label { color: #91a8b1 !important; }
.primary-btn { background: var(--lime) !important; color: #07120d !important; border-radius: 9px; font-weight: 750; min-height: 46px; }
.secondary-btn { background: #122129 !important; color: #eaf2ef !important; border: 1px solid #34515c; border-radius: 9px; }
.danger-btn { background: #d85d58 !important; color: #fff !important; border-radius: 9px; }
.link-btn { color: #73e4b7 !important; }
.workflow-card { width: 100%; min-height: 105px; padding: 20px 22px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; cursor: pointer; transition: .15s ease; }
.workflow-card:hover { background: #15262c; border-color: #578476; }
.workflow-card.active { background: #123126; border-color: #72d7aa; box-shadow: none; }
.workflow-number { color: #86a7b5; font-size: 12px; font-weight: 800; }
.workflow-title { color: #fff; font-size: 15px; font-weight: 700; }
.workflow-description { color: #91aab5; font-size: 12px; }
.divider { width: 100%; height: 1px; background: var(--border); }
.upload-zone { width: 100%; min-height: 112px; background: #0b171c; border: 1px dashed #385661; border-radius: 10px; }
.upload-zone .q-uploader__header { background: #14272d; color: #eaf2ef; }
.upload-zone .q-uploader__list { padding: 12px 14px; }
.metric { flex: 1 1 0; min-width: 145px; padding: 16px 20px; background: var(--panel); border: 1px solid var(--border); border-radius: 12px; }
.metric .eyebrow, .metric-label { color: #91aab5; font-size: 11px; letter-spacing: .04em; }
.status-pill { border-radius: 999px; padding: 4px 9px; font-size: 11px; font-weight: 700; }
.status-success { color: #74e7bb; background: rgba(101,213,167,.11); border: 1px solid rgba(101,213,167,.38); }
.status-warning { color: #ffd17e; background: rgba(245,184,91,.11); border: 1px solid rgba(245,184,91,.38); }
.status-danger { color: #ff9f99; background: rgba(255,119,111,.11); border: 1px solid rgba(255,119,111,.38); }
.status-neutral { color: #b9ccd4; background: rgba(143,170,181,.10); border: 1px solid rgba(143,170,181,.3); }
.processing { padding: 18px 20px; background: #10271f; border: 1px solid #376c58; border-radius: 10px; }
.amat-table { background: #0d181e; border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.amat-table thead tr { background: #17252c; }
.amat-table th { color: #91acb8; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; }
.amat-table td { color: #e9f2ef; border-color: #1d3038 !important; }
.q-dialog__inner > div, .q-menu { background: var(--panel); color: var(--text); }
.q-linear-progress__model { color: var(--lime) !important; }
@media (max-width: 850px) {
  .login-feature { display: none !important; }
  .login-form { min-height: 520px; }
  .page-wrap { width: min(100% - 28px, 1060px); padding-top: 28px; }
  .workflow-row { flex-direction: column !important; }
  .desktop-only { display: none !important; }
}
"""
