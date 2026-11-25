//! AI Organization 데스크톱 앱.
//!
//! - 내장 백엔드(`ai-org-server`, PyInstaller 단일 실행 파일)를 루프백 임의 포트로 띄우고, 준비되면 창을 그 주소로 연다.
//! - 시스템 트레이: 실행 중 에이전트 수·승인 대기·사용량을 3초마다 갱신(백엔드 `/api/v1/desktop/summary`).
//! - 네이티브 알림: 백엔드 알림 센터의 새 알림(승인 요청·작업 완료/실패·사용량 경고)을 OS 알림으로 보낸다.
//! - 창을 닫으면 트레이로 숨고, 트레이의 '종료'로 끝낸다. 앱이 끝나면 백엔드 표준 입력이 닫혀 백엔드도 끝난다.
//!
//! 데스크톱 요약 API는 앱이 띄울 때 만든 임의 토큰으로만 열린다(다른 로컬 프로세스가 읽지 못하게).
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use serde::Deserialize;
use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIcon, TrayIconBuilder, TrayIconEvent};
use tauri::{AppHandle, Manager, RunEvent, Url, WindowEvent, Wry};
use tauri_plugin_notification::NotificationExt;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

const START_TIMEOUT: Duration = Duration::from_secs(120);
const POLL_INTERVAL: Duration = Duration::from_secs(3);

/// 내장 백엔드 프로세스. 앱이 끝날 때 버려(drop) 표준 입력을 닫는다.
struct Backend {
    child: Mutex<Option<CommandChild>>,
}

#[derive(Clone)]
struct TrayItems {
    tray: TrayIcon<Wry>,
    status: MenuItem<Wry>,
    approvals: MenuItem<Wry>,
    usage: MenuItem<Wry>,
}

#[derive(Deserialize)]
struct Usage {
    provider: String,
    label: String,
    percent: f64,
}

#[derive(Deserialize)]
struct Note {
    title: String,
    body: String,
}

#[derive(Deserialize)]
struct Summary {
    running: u32,
    approvals: u32,
    usage: Vec<Usage>,
    notifications: Vec<Note>,
    latest_id: u64,
}

/// 백엔드 포트: 테스트용 `AI_ORG_DESKTOP_PORT`가 있으면 그 값, 없으면 OS가 고른 빈 포트.
fn pick_port() -> u16 {
    if let Some(port) = std::env::var("AI_ORG_DESKTOP_PORT").ok().and_then(|p| p.parse().ok()) {
        return port;
    }
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8765)
}

/// 루프백 HTTP GET(의존성 없이). 응답 상태 코드와 본문을 돌려준다.
fn http_get(port: u16, path: &str, token: &str) -> Option<(u16, String)> {
    let addr = SocketAddr::from(([127, 0, 0, 1], port));
    let mut stream = TcpStream::connect_timeout(&addr, Duration::from_secs(2)).ok()?;
    stream.set_read_timeout(Some(Duration::from_secs(5))).ok()?;
    write!(
        stream,
        "GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nAuthorization: Bearer {token}\r\nConnection: close\r\n\r\n"
    )
    .ok()?;
    let mut raw = Vec::new();
    stream.read_to_end(&mut raw).ok()?;
    let text = String::from_utf8_lossy(&raw);
    let (head, body) = text.split_once("\r\n\r\n")?;
    let code = head.split_whitespace().nth(1)?.parse().ok()?;
    Some((code, body.to_string()))
}

fn show_main(app: &AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// 시작 화면에 오류를 보이고 트레이에도 적는다.
fn show_error(app: &AppHandle, items: &TrayItems, message: &str) {
    let _ = items.status.set_text(message);
    let _ = items.tray.set_tooltip(Some(format!("AI Organization — {message}")));
    if let Some(window) = app.get_webview_window("main") {
        let js = format!(
            "var e=document.getElementById('error');if(e){{e.hidden=false;e.textContent={};}}",
            serde_json::to_string(message).unwrap_or_default()
        );
        let _ = window.eval(js);
    }
}

fn apply_summary(app: &AppHandle, items: &TrayItems, summary: &Summary) {
    let _ = items.status.set_text(format!("실행 중인 에이전트 {}", summary.running));
    let _ = items.approvals.set_text(format!("승인 대기 {}", summary.approvals));
    let usage = summary
        .usage
        .iter()
        .map(|u| format!("{} {} {:.0}%", u.provider, u.label, u.percent))
        .collect::<Vec<_>>()
        .join(" · ");
    let _ = items.usage.set_text(if usage.is_empty() { "사용량: 표시할 값 없음".to_string() } else { usage });
    let _ = items.tray.set_tooltip(Some(format!(
        "AI Organization — 실행 중 {} · 승인 대기 {}",
        summary.running, summary.approvals
    )));
    for note in &summary.notifications {
        let _ = app.notification().builder().title(&note.title).body(&note.body).show();
    }
}

/// 백엔드가 뜰 때까지 기다렸다가 창을 열고, 이후 요약을 주기적으로 가져온다.
fn monitor(app: AppHandle, port: u16, token: String, items: TrayItems) {
    let started = Instant::now();
    loop {
        if matches!(http_get(port, "/api/v1/system/health", &token), Some((200, _))) {
            break;
        }
        if started.elapsed() > START_TIMEOUT {
            show_error(&app, &items, "로컬 서버를 시작하지 못했습니다. 앱을 다시 실행해 주세요.");
            return;
        }
        thread::sleep(Duration::from_millis(500));
    }
    if let (Some(window), Ok(url)) = (
        app.get_webview_window("main"),
        Url::parse(&format!("http://127.0.0.1:{port}/?desktop=1")),
    ) {
        let _ = window.navigate(url);
    }
    let mut after = 0u64;
    loop {
        match http_get(port, &format!("/api/v1/desktop/summary?after={after}"), &token) {
            Some((200, body)) => {
                if let Ok(summary) = serde_json::from_str::<Summary>(&body) {
                    apply_summary(&app, &items, &summary);
                    after = after.max(summary.latest_id);
                }
            }
            _ => {
                let _ = items.status.set_text("로컬 서버 응답 없음");
            }
        }
        thread::sleep(POLL_INTERVAL);
    }
}

fn main() {
    tauri::Builder::default()
        // 두 번째 실행은 새 백엔드를 띄우지 않고 기존 창을 연다(같은 DB를 두 서버가 쓰지 않게).
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| show_main(app)))
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            let port = pick_port();
            let token = format!("{}{}", uuid::Uuid::new_v4().simple(), uuid::Uuid::new_v4().simple());

            // 백엔드를 먼저 띄운다. 트레이 초기화가 느린 환경(D-Bus 응답 대기)에서도 서버 시작이 늦어지지 않게.
            let (mut events, child) = app
                .shell()
                .sidecar("ai-org-server")?
                .env("AI_ORG_PORT", port.to_string())
                .env("AI_ORG_WEB_PORT", port.to_string())
                .env("AI_ORG_DESKTOP_TOKEN", &token)
                .env("AI_ORG_EXIT_ON_STDIN_EOF", "1")
                .spawn()?;
            app.manage(Backend { child: Mutex::new(Some(child)) });

            let open = MenuItem::with_id(app, "open", "열기", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let status = MenuItem::with_id(app, "status", "로컬 서버 시작 중…", false, None::<&str>)?;
            let approvals = MenuItem::with_id(app, "approvals", "승인 대기 —", false, None::<&str>)?;
            let usage = MenuItem::with_id(app, "usage", "사용량 —", false, None::<&str>)?;
            let separator = PredefinedMenuItem::separator(app)?;
            let menu = Menu::with_items(app, &[&status, &approvals, &usage, &separator, &open, &quit])?;
            let mut builder = TrayIconBuilder::with_id("main")
                .tooltip("AI Organization")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_main(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        show_main(tray.app_handle());
                    }
                });
            if let Some(icon) = app.default_window_icon() {
                builder = builder.icon(icon.clone());
            }
            let tray = builder.build(app)?;
            let items = TrayItems { tray, status, approvals, usage };

            // 백엔드 출력은 앱 로그(표준 오류)로 넘기고, 백엔드가 죽으면 알린다.
            let handle = app.handle().clone();
            let crash_items = items.clone();
            tauri::async_runtime::spawn(async move {
                while let Some(event) = events.recv().await {
                    match event {
                        CommandEvent::Stdout(line) | CommandEvent::Stderr(line) => {
                            eprintln!("[ai-org-server] {}", String::from_utf8_lossy(&line).trim_end());
                        }
                        CommandEvent::Terminated(payload) => {
                            show_error(
                                &handle,
                                &crash_items,
                                &format!("로컬 서버가 종료되었습니다(코드 {:?}).", payload.code),
                            );
                        }
                        _ => {}
                    }
                }
            });

            let handle = app.handle().clone();
            thread::spawn(move || monitor(handle, port, token, items));
            Ok(())
        })
        .on_window_event(|window, event| {
            // 창을 닫으면 트레이로 숨긴다(에이전트 작업과 알림은 계속). 종료는 트레이 메뉴에서.
            if let WindowEvent::CloseRequested { api, .. } = event {
                let _ = window.hide();
                api.prevent_close();
            }
        })
        .build(tauri::generate_context!())
        .expect("AI Organization 앱을 시작하지 못했습니다")
        .run(|app, event| {
            if let RunEvent::Exit = event {
                // 표준 입력을 닫아 백엔드가 정상 종료하게 한다(실행 중 작업을 정리하고 끝남).
                if let Some(child) = app.state::<Backend>().child.lock().ok().and_then(|mut c| c.take()) {
                    drop(child);
                }
            }
        });
}
