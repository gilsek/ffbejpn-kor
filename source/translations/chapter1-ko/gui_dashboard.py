"""File-driven GUI for monitoring FFBE GalTransl localization work."""

from __future__ import annotations

import csv
import json
import os
import queue
import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

PROJECT_DIR = Path(__file__).resolve().parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

import pipeline_core
import time_policy
import usage_monitor


BG_MAIN = "#181825"
BG_CARD = "#1e1e2e"
BG_CARD_LIGHT = "#28283d"
BG_HEADER = "#11111b"
TEXT_PRIMARY = "#cdd6f4"
TEXT_SECONDARY = "#a6adc8"
TEXT_MUTED = "#6c7086"
ACCENT_BLUE = "#89b4fa"
ACCENT_GREEN = "#a6e3a1"
ACCENT_YELLOW = "#f9e2af"
ACCENT_RED = "#f38ba8"
ACCENT_PURPLE = "#cba6f7"
BORDER_COLOR = "#313244"


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "계산 불가"
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours}시간 {minutes}분"
    if minutes:
        return f"{minutes}분 {secs}초"
    return f"{secs}초"


class FFBEPipelineDashboard:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("FFBE Memorial 번역 파이프라인 관제")
        self.root.geometry("1320x900")
        self.root.minsize(1080, 720)
        self.root.configure(bg=BG_MAIN)
        self.runtime_dir = PROJECT_DIR / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.monitoring_state_path = self.runtime_dir / "monitoring_mode.json"
        self.snapshot: dict[str, Any] = {}
        self.refreshing = False
        self.runner: pipeline_core.TranslationRunner | None = None
        self.proxy: usage_monitor.UsageProxyProcess | None = None
        self.audit_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.log_queue: queue.Queue[str] = queue.Queue()
        self.metrics: dict[str, tk.StringVar] = {}
        self.profile_vars: dict[str, tk.StringVar] = {}
        self.csv_records: dict[str, dict[str, Any]] = {}
        self.current_csv_rows: list[list[str]] = []
        self.current_csv_headers: list[str] = []
        self.visible_issues: dict[str, dict[str, Any]] = {}
        self.selected_issue: dict[str, Any] | None = None
        self.qa_context: dict[str, Any] = {}
        self.issue_filter = tk.StringVar(value="output")
        self._auto_refresh_scheduled = False

        self.setup_styles()
        self.build_ui()
        self.ensure_pricing_defaults()
        self.schedule_market_clock()
        self.request_refresh()
        self.root.after(100, self.poll_queues)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def setup_styles(self) -> None:
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=BG_MAIN, foreground=TEXT_PRIMARY)
        style.configure("TFrame", background=BG_MAIN)
        style.configure("Card.TFrame", background=BG_CARD)
        style.configure("TLabel", background=BG_MAIN, foreground=TEXT_PRIMARY)
        style.configure("Header.TLabel", background=BG_HEADER, foreground="#ffffff")
        style.configure("Title.TLabel", background=BG_HEADER, foreground="#ffffff", font=("Malgun Gothic", 15, "bold"))
        style.configure("Sub.TLabel", background=BG_HEADER, foreground=TEXT_SECONDARY, font=("Malgun Gothic", 9))
        style.configure("CardTitle.TLabel", background=BG_CARD, foreground=ACCENT_BLUE, font=("Malgun Gothic", 10, "bold"))
        style.configure("Metric.TLabel", background=BG_CARD, foreground=ACCENT_GREEN, font=("Segoe UI", 17, "bold"))
        style.configure("MetricCaption.TLabel", background=BG_CARD, foreground=TEXT_MUTED, font=("Malgun Gothic", 8))
        style.configure("Muted.TLabel", background=BG_MAIN, foreground=TEXT_MUTED, font=("Malgun Gothic", 8))
        style.configure("TButton", font=("Malgun Gothic", 9), padding=(9, 5))
        style.configure("Horizontal.TProgressbar", background=ACCENT_GREEN, troughcolor=BG_CARD_LIGHT, borderwidth=0)
        style.configure(
            "Treeview",
            background=BG_CARD,
            fieldbackground=BG_CARD,
            foreground=TEXT_PRIMARY,
            rowheight=25,
            font=("Malgun Gothic", 9),
            borderwidth=0,
        )
        style.configure(
            "Treeview.Heading",
            background=BG_CARD_LIGHT,
            foreground=TEXT_PRIMARY,
            font=("Malgun Gothic", 9, "bold"),
        )
        style.map("Treeview", background=[("selected", "#45475a")])
        style.configure("TNotebook", background=BG_MAIN, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_CARD_LIGHT, foreground=TEXT_SECONDARY, padding=(12, 6))
        style.map("TNotebook.Tab", background=[("selected", BG_CARD)], foreground=[("selected", ACCENT_BLUE)])

    def build_ui(self) -> None:
        header = tk.Frame(self.root, bg=BG_HEADER, padx=18, pady=11)
        header.pack(fill="x")
        title_box = tk.Frame(header, bg=BG_HEADER)
        title_box.pack(side="left")
        ttk.Label(
            title_box,
            text="FFBE Memorial 번역 파이프라인 관제",
            style="Title.TLabel",
        ).pack(anchor="w")
        self.profile_summary = ttk.Label(
            title_box,
            text="파일 상태를 확인하는 중입니다.",
            style="Sub.TLabel",
        )
        self.profile_summary.pack(anchor="w")
        self.status_badge = tk.Label(
            header,
            text="● 점검 중",
            bg="#3e3820",
            fg=ACCENT_YELLOW,
            font=("Malgun Gothic", 10, "bold"),
            padx=12,
            pady=5,
        )
        self.status_badge.pack(side="right")

        toolbar = tk.Frame(self.root, bg=BG_CARD_LIGHT, padx=12, pady=7)
        toolbar.pack(fill="x")
        self.btn_refresh = tk.Button(
            toolbar,
            text="상태 새로고침",
            command=self.request_refresh,
            bg="#313244",
            fg=TEXT_PRIMARY,
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
        )
        self.btn_refresh.pack(side="left", padx=3)
        self.btn_start = tk.Button(
            toolbar,
            text="GalTransl 실행",
            command=self.start_translation,
            bg="#2e7d32",
            fg="white",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
        )
        self.btn_start.pack(side="left", padx=3)
        self.btn_stop = tk.Button(
            toolbar,
            text="실행 중지",
            command=self.stop_translation,
            bg="#c62828",
            fg="white",
            relief="flat",
            padx=12,
            pady=4,
            cursor="hand2",
            state="disabled",
        )
        self.btn_stop.pack(side="left", padx=3)
        tk.Button(
            toolbar,
            text="CSV 폴더",
            command=lambda: self.open_path(pipeline_core.CSV_DIR),
            bg="#45475a",
            fg="white",
            relief="flat",
            padx=10,
            pady=4,
        ).pack(side="right", padx=3)
        tk.Button(
            toolbar,
            text="런타임 폴더",
            command=lambda: self.open_path(self.runtime_dir),
            bg="#45475a",
            fg="white",
            relief="flat",
            padx=10,
            pady=4,
        ).pack(side="right", padx=3)

        metrics = tk.Frame(self.root, bg=BG_MAIN, padx=12, pady=8)
        metrics.pack(fill="x")
        for column, (key, caption) in enumerate(
            [
                ("progress", "행 기준 진행률"),
                ("files", "완료 파일"),
                ("rows", "번역 행"),
                ("source", "일본어 원문 상태"),
                ("quality", "번역 QA 경고"),
                ("cost", "계량된 비용"),
                ("tokens", "토큰 사용"),
                ("eta", "남은 시간"),
            ]
        ):
            card = tk.Frame(metrics, bg=BG_CARD, padx=10, pady=7, highlightthickness=1, highlightbackground=BORDER_COLOR)
            card.grid(row=0, column=column, sticky="nsew", padx=3)
            metrics.grid_columnconfigure(column, weight=1)
            variable = tk.StringVar(value="—")
            ttk.Label(card, textvariable=variable, style="Metric.TLabel").pack(anchor="w")
            ttk.Label(card, text=caption, style="MetricCaption.TLabel").pack(anchor="w")
            self.metrics[key] = variable

        progress_row = tk.Frame(self.root, bg=BG_MAIN, padx=15, pady=0)
        progress_row.pack(fill="x")
        self.progress_bar = ttk.Progressbar(progress_row, mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 8))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        self.build_files_tab()
        self.build_quality_tab()
        self.build_input_tab()
        self.build_data_tab()
        self.build_run_tab()
        self.build_log_panel()

    def build_files_tab(self) -> None:
        tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(tab, text="파일 진행")
        ttk.Label(tab, text="파일별 진행률은 gt_input / gt_output / transl_cache를 직접 비교해 계산합니다.", style="Muted.TLabel").pack(anchor="w", padx=8, pady=6)
        columns = ("status", "file", "rows", "completed", "chars", "issues")
        self.file_tree = ttk.Treeview(tab, columns=columns, show="headings")
        for key, label, width, anchor in [
            ("status", "상태", 100, "center"),
            ("file", "파일", 180, "w"),
            ("rows", "행", 70, "center"),
            ("completed", "완료", 80, "center"),
            ("chars", "원문 자수", 100, "center"),
            ("issues", "이슈", 80, "center"),
        ]:
            self.file_tree.heading(key, text=label)
            self.file_tree.column(key, width=width, anchor=anchor)
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.file_tree.yview)
        self.file_tree.configure(yscrollcommand=scroll.set)
        self.file_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        scroll.pack(side="right", fill="y", pady=(0, 8), padx=(0, 8))
        self.file_tree.tag_configure("translated", foreground=ACCENT_GREEN)
        self.file_tree.tag_configure("qa_warning", foreground=ACCENT_YELLOW)
        self.file_tree.tag_configure("blocked", foreground=ACCENT_RED)
        self.file_tree.tag_configure("source_warning", foreground=ACCENT_YELLOW)
        self.file_tree.tag_configure("pending", foreground=TEXT_MUTED)

    def build_quality_tab(self) -> None:
        tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(tab, text="번역 QA")
        controls = tk.Frame(tab, bg=BG_MAIN)
        controls.pack(fill="x", padx=8, pady=6)
        ttk.Label(controls, text="검사 범위:", style="Muted.TLabel").pack(side="left")
        filter_box = ttk.Combobox(
            controls,
            textvariable=self.issue_filter,
            values=["전체", "source", "output", "meta"],
            state="readonly",
            width=12,
        )
        filter_box.pack(side="left", padx=6)
        filter_box.bind("<<ComboboxSelected>>", lambda _event: self.populate_issues())
        self.quality_summary = ttk.Label(controls, text="", style="Muted.TLabel")
        self.quality_summary.pack(side="left", padx=12)
        pane = tk.PanedWindow(tab, orient="vertical", bg=BG_MAIN, sashwidth=5)
        pane.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        issue_frame = tk.Frame(pane, bg=BG_CARD)
        columns = ("scope", "type", "file", "id", "reason")
        self.issue_tree = ttk.Treeview(issue_frame, columns=columns, show="headings")
        for key, label, width in [
            ("scope", "범위", 80),
            ("type", "유형", 190),
            ("file", "파일", 160),
            ("id", "FFBE ID", 100),
            ("reason", "문제 내용", 650),
        ]:
            self.issue_tree.heading(key, text=label)
            self.issue_tree.column(
                key,
                width=width,
                anchor="w" if key in {"file", "reason"} else "center",
            )
        scroll = ttk.Scrollbar(issue_frame, orient="vertical", command=self.issue_tree.yview)
        self.issue_tree.configure(yscrollcommand=scroll.set)
        self.issue_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.issue_tree.bind("<<TreeviewSelect>>", self.on_issue_selected)
        pane.add(issue_frame, minsize=220)

        detail = tk.Frame(pane, bg=BG_CARD, padx=8, pady=6)
        self.qa_detail_label = tk.Label(
            detail,
            text="검수할 QA 항목을 선택하세요.",
            bg=BG_CARD,
            fg=ACCENT_BLUE,
            font=("Malgun Gothic", 9, "bold"),
            anchor="w",
        )
        self.qa_detail_label.pack(fill="x")
        self.qa_reason_label = tk.Label(
            detail,
            text="",
            bg=BG_CARD,
            fg=ACCENT_YELLOW,
            font=("Malgun Gothic", 9),
            justify="left",
            anchor="w",
            wraplength=1220,
        )
        self.qa_reason_label.pack(fill="x", pady=(3, 3))
        text_grid = tk.Frame(detail, bg=BG_CARD)
        text_grid.pack(fill="both", expand=True, pady=(4, 0))
        for column, label in enumerate(("일본어 원문", "영어 참고", "한국어 번역")):
            ttk.Label(text_grid, text=label, style="CardTitle.TLabel").grid(
                row=0, column=column, sticky="w", padx=4
            )
            text_widget = tk.Text(
                text_grid,
                height=7,
                wrap="word",
                bg="#11111b",
                fg=TEXT_PRIMARY,
                relief="flat",
                padx=6,
                pady=5,
                font=("Malgun Gothic", 9),
            )
            text_widget.grid(
                row=1,
                column=column,
                sticky="nsew",
                padx=4,
                pady=(2, 4),
            )
            text_grid.grid_columnconfigure(column, weight=1)
            if column == 0:
                self.qa_source_text = text_widget
            elif column == 1:
                self.qa_english_text = text_widget
            else:
                self.qa_translation_edit = text_widget
        self.qa_source_text.config(state="disabled")
        self.qa_english_text.config(state="disabled")

        actions = tk.Frame(detail, bg=BG_CARD)
        actions.pack(fill="x")
        self.qa_action_label = ttk.Label(actions, text="", style="Muted.TLabel")
        self.qa_action_label.pack(side="left")
        tk.Button(
            actions,
            text="번역 수정 저장",
            command=self.save_issue_translation,
            bg="#1565c0",
            fg="white",
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="right", padx=4)
        tk.Button(
            actions,
            text="문제 없음으로 승인",
            command=self.accept_selected_issue,
            bg="#2e7d32",
            fg="white",
            relief="flat",
            padx=12,
            pady=4,
        ).pack(side="right", padx=4)
        pane.add(detail, minsize=210)

    def build_input_tab(self) -> None:
        tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(tab, text="일본어 입력")
        self.input_summary = tk.Text(
            tab,
            height=11,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            relief="flat",
            wrap="word",
            padx=12,
            pady=10,
            font=("Malgun Gothic", 10),
        )
        self.input_summary.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(
            tab,
            text="원문 이슈와 메타데이터 연결 상태",
            style="Muted.TLabel",
        ).pack(anchor="w", padx=10, pady=(4, 2))
        columns = ("type", "file", "id", "detail")
        self.input_issue_tree = ttk.Treeview(tab, columns=columns, show="headings")
        for key, label, width in [
            ("type", "유형", 200),
            ("file", "파일", 180),
            ("id", "FFBE ID", 120),
            ("detail", "내용", 600),
        ]:
            self.input_issue_tree.heading(key, text=label)
            self.input_issue_tree.column(key, width=width, anchor="w" if key in {"file", "detail"} else "center")
        scroll = ttk.Scrollbar(tab, orient="vertical", command=self.input_issue_tree.yview)
        self.input_issue_tree.configure(yscrollcommand=scroll.set)
        self.input_issue_tree.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        scroll.pack(side="right", fill="y", pady=(0, 8), padx=(0, 8))

    def build_data_tab(self) -> None:
        tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(tab, text="번역 데이터")
        controls = tk.Frame(tab, bg=BG_MAIN)
        controls.pack(fill="x", padx=8, pady=6)
        ttk.Label(controls, text="CSV:", style="Muted.TLabel").pack(side="left")
        self.csv_selector = ttk.Combobox(controls, state="readonly", width=42)
        self.csv_selector.pack(side="left", padx=6)
        self.csv_selector.bind("<<ComboboxSelected>>", self.load_selected_csv)
        self.csv_count = ttk.Label(controls, text="", style="Muted.TLabel")
        self.csv_count.pack(side="right")

        pane = tk.PanedWindow(tab, orient="vertical", bg=BG_MAIN, sashwidth=5)
        pane.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        tree_frame = tk.Frame(pane, bg=BG_CARD)
        self.csv_tree = ttk.Treeview(tree_frame, show="headings")
        csv_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical", command=self.csv_tree.yview)
        csv_scroll_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.csv_tree.xview)
        self.csv_tree.configure(yscrollcommand=csv_scroll_y.set, xscrollcommand=csv_scroll_x.set)
        self.csv_tree.pack(side="left", fill="both", expand=True)
        csv_scroll_y.pack(side="right", fill="y")
        csv_scroll_x.pack(side="bottom", fill="x")
        self.csv_tree.bind("<<TreeviewSelect>>", self.show_selected_csv_row)
        pane.add(tree_frame, minsize=250)
        self.csv_detail = tk.Text(
            pane,
            height=7,
            bg="#11111b",
            fg=TEXT_PRIMARY,
            relief="flat",
            wrap="word",
            padx=8,
            pady=6,
            font=("Malgun Gothic", 9),
        )
        pane.add(self.csv_detail, minsize=120)

    def build_run_tab(self) -> None:
        tab = ttk.Frame(self.notebook, style="TFrame")
        self.notebook.add(tab, text="실행·비용")
        top = tk.Frame(tab, bg=BG_CARD, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER_COLOR)
        top.pack(fill="x", padx=8, pady=8)
        selection = tk.Frame(top, bg=BG_CARD)
        selection.pack(fill="x", pady=(0, 6))
        tk.Label(selection, text="번역 모델 선택", width=15, anchor="w", bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")
        self.provider_choice = tk.StringVar()
        self.provider_combo = ttk.Combobox(selection, textvariable=self.provider_choice, state="readonly", width=31,
                                           values=tuple(
                                               profile["label"]
                                               for profile in pipeline_core.TRANSLATION_PROVIDER_PROFILES.values()
                                           ))
        self.provider_combo.pack(side="left", padx=(0, 8))
        ttk.Button(selection, text="설정 적용", command=self.apply_provider).pack(side="left")
        tk.Label(top, text="KeyRouter는 안정 모드(1 worker·16행·자동 백오프)로 전환하며 FFBE 요청의 모델 fallback은 차단됩니다.",
                 bg=BG_CARD, fg=ACCENT_YELLOW, anchor="w").pack(fill="x", pady=(0, 4))
        for key, label in [
            ("model", "모델"),
            ("endpoint", "엔드포인트"),
            ("workers", "워커"),
            ("batch", "요청당 행"),
            ("context", "문맥 행"),
            ("retries", "API 재시도"),
            ("error_wait", "오류 대기"),
            ("worker_adjust", "워커 자동 조정"),
            ("backend", "GalTransl 백엔드"),
        ]:
            row = tk.Frame(top, bg=BG_CARD)
            row.pack(fill="x", pady=2)
            tk.Label(row, text=label, width=15, anchor="w", bg=BG_CARD, fg=TEXT_MUTED).pack(side="left")
            variable = tk.StringVar(value="—")
            tk.Label(row, textvariable=variable, anchor="w", bg=BG_CARD, fg=TEXT_PRIMARY, font=("Consolas", 9)).pack(side="left", fill="x", expand=True)
            self.profile_vars[key] = variable

        pricing_box = tk.LabelFrame(
            tab,
            text="DeepSeek 참고 단가 (KeyRouter에는 적용되지 않음, USD / 100만 토큰)",
            bg=BG_MAIN,
            fg=ACCENT_BLUE,
            padx=10,
            pady=8,
            labelanchor="nw",
        )
        pricing_box.pack(fill="x", padx=8, pady=(2, 8))
        self.price_model = tk.StringVar()
        self.market_status_label = tk.Label(
            pricing_box,
            text="현재 구간 계산 중",
            bg=BG_CARD,
            fg=ACCENT_YELLOW,
            font=("Malgun Gothic", 11, "bold"),
            padx=10,
            pady=5,
            anchor="w",
        )
        self.market_status_label.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 4))
        self.market_countdown_label = tk.Label(
            pricing_box,
            text="",
            bg=BG_MAIN,
            fg=TEXT_PRIMARY,
            font=("Consolas", 11, "bold"),
            anchor="w",
        )
        self.market_countdown_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=2)
        self.market_rate_label = tk.Label(
            pricing_box,
            text="",
            bg=BG_MAIN,
            fg=TEXT_SECONDARY,
            font=("Consolas", 9),
            justify="left",
            anchor="w",
        )
        self.market_rate_label.grid(row=2, column=0, columnspan=2, sticky="ew", pady=2)
        self.market_holiday_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            pricing_box,
            text="오늘을 중국 공휴일로 간주 (종일 오프피크)",
            variable=self.market_holiday_var,
            command=self.update_market_clock,
            bg=BG_MAIN,
            fg=TEXT_SECONDARY,
            selectcolor=BG_CARD,
            activebackground=BG_MAIN,
            activeforeground=TEXT_PRIMARY,
            font=("Malgun Gothic", 9),
            anchor="w",
        ).grid(row=3, column=0, sticky="w", pady=(5, 0))
        tk.Label(
            pricing_box,
            text="평일 피크: 10:00–13:00, 15:00–19:00 KST · 주말/공휴일 종일 오프피크",
            bg=BG_MAIN,
            fg=TEXT_MUTED,
            font=("Malgun Gothic", 8),
            anchor="w",
        ).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(3, 0))
        pricing_box.grid_columnconfigure(0, weight=1)

        proxy_box = tk.Frame(tab, bg=BG_CARD_LIGHT, padx=10, pady=7)
        proxy_box.pack(fill="x", padx=8, pady=(0, 8))
        tk.Label(proxy_box, text="정확한 토큰·비용 계량", bg=BG_CARD_LIGHT, fg=ACCENT_BLUE, font=("Malgun Gothic", 9, "bold")).pack(side="left")
        self.proxy_status = tk.Label(
            proxy_box,
            text="중지됨",
            bg=BG_CARD_LIGHT,
            fg=TEXT_MUTED,
            font=("Malgun Gothic", 9),
        )
        self.proxy_status.pack(side="left", padx=12)
        tk.Button(
            proxy_box,
            text="모니터링 모드 시작",
            command=self.enable_monitoring_mode,
            bg="#1565c0",
            fg="white",
            relief="flat",
            padx=10,
            pady=3,
        ).pack(side="right", padx=3)
        tk.Button(
            proxy_box,
            text="원래 엔드포인트 복구",
            command=self.disable_monitoring_mode,
            bg="#45475a",
            fg="white",
            relief="flat",
            padx=10,
            pady=3,
        ).pack(side="right", padx=3)

        self.usage_summary = tk.Text(
            tab,
            height=10,
            bg=BG_CARD,
            fg=TEXT_PRIMARY,
            relief="flat",
            wrap="word",
            padx=12,
            pady=10,
            font=("Consolas", 9),
        )
        self.usage_summary.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def build_log_panel(self) -> None:
        bottom = tk.Frame(self.root, bg=BG_CARD, padx=10, pady=5)
        bottom.pack(fill="x", side="bottom")
        tk.Label(bottom, text="실행 로그", bg=BG_CARD, fg=ACCENT_BLUE, font=("Malgun Gothic", 9, "bold")).pack(anchor="w")
        body = tk.Frame(bottom, bg=BG_CARD)
        body.pack(fill="x")
        self.log_text = tk.Text(body, height=7, bg="#11111b", fg=TEXT_SECONDARY, relief="flat", padx=6, pady=4, font=("Consolas", 8))
        scroll = ttk.Scrollbar(body, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scroll.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def ensure_pricing_defaults(self) -> None:
        profile = pipeline_core.read_galtransl_profile()
        model = profile.get("model") or ""
        self.price_model.set(model)
        usage_monitor.load_pricing()
        self.update_market_clock()

    def apply_provider(self) -> None:
        selected_label = self.provider_choice.get()
        provider = next(
            (
                key
                for key, profile in pipeline_core.TRANSLATION_PROVIDER_PROFILES.items()
                if profile["label"] == selected_label
            ),
            None,
        )
        if not provider:
            messagebox.showwarning("모델 선택", "적용할 모델을 선택하세요.")
            return
        if self.refreshing or (self.runner and self.runner.is_running()) or self.read_run_state().get("status") in {"running", "pending"}:
            messagebox.showwarning("모델 선택", "번역 실행 또는 상태 갱신이 끝난 뒤 변경하세요.")
            return
        if self.read_monitoring_state().get("active") or (self.proxy and self.proxy.is_running()):
            messagebox.showwarning("모델 선택", "모니터링 프록시를 먼저 중지하고 변경하세요.")
            return
        try:
            pipeline_core.select_translation_provider(pipeline_core.CONFIG_PATH, provider)
        except (OSError, ValueError) as exc:
            messagebox.showerror("모델 변경 실패", str(exc))
            return
        self.append_log(f"[설정] 번역 모델 변경: {provider}")
        self.request_refresh()
        messagebox.showinfo("모델 변경", "설정을 저장했습니다. 다음 번역 실행부터 적용됩니다.")

    def schedule_market_clock(self) -> None:
        self.update_market_clock()
        self.root.after(1000, self.schedule_market_clock)

    def update_market_clock(self) -> None:
        holiday = bool(self.market_holiday_var.get())
        clock = time_policy.market_clock(holiday=holiday)
        period = clock["period"]
        status = "피크 시간" if period == "peak" else "오프피크 시간"
        color = ACCENT_RED if period == "peak" else ACCENT_GREEN
        local_time = time.strftime("%Y-%m-%d %H:%M:%S KST")
        self.market_status_label.config(
            text=f"현재 {status} · {local_time}",
            fg=color,
        )
        self.market_countdown_label.config(
            text=(
                f"{clock['transition_label']}까지 "
                f"{time_policy.format_countdown(clock['remaining_seconds'])} "
                f"· {clock['transition_at_kst']}"
            )
        )
        model = self.price_model.get() or "deepseek-flash"
        pricing = usage_monitor.load_pricing()
        model_rates = pricing.get("models", {}).get(model, {})
        if not isinstance(model_rates, dict):
            model_rates = {}
        peak_rates = model_rates.get("peak", {})
        off_peak_rates = model_rates.get("off_peak", {})
        if not isinstance(peak_rates, dict) or not isinstance(off_peak_rates, dict):
            peak_rates = {}
            off_peak_rates = {}
        current_rates = peak_rates if period == "peak" else off_peak_rates
        self.market_rate_label.config(
            text=(
                f"모델: {model}   현재 입력 ${current_rates.get('input_per_million', '—')}"
                f" / 캐시 ${current_rates.get('cached_input_per_million', '—')}"
                f" / 출력 ${current_rates.get('output_per_million', '—')} per 1M\n"
                f"피크 입력 ${peak_rates.get('input_per_million', '—')} · "
                f"오프피크 입력 ${off_peak_rates.get('input_per_million', '—')} "
                f"(오프피크 50% 할인)\n"
                f"정책 출처: {time_policy.POLICY_SOURCE} "
                f"(확인일 {time_policy.POLICY_CHECKED_AT})"
            )
        )

    def request_refresh(self) -> None:
        if self.refreshing:
            return
        self.refreshing = True
        self.btn_refresh.config(state="disabled")
        self.status_badge.config(text="● 점검 중", bg="#3e3820", fg=ACCENT_YELLOW)
        threading.Thread(target=self.audit_worker, daemon=True).start()

    def audit_worker(self) -> None:
        try:
            result = pipeline_core.audit_project(PROJECT_DIR, self.runtime_dir, write_snapshot=True)
            self.audit_queue.put(("ok", result))
        except Exception as exc:
            self.audit_queue.put(("error", f"{type(exc).__name__}: {exc}"))

    def poll_queues(self) -> None:
        try:
            while True:
                try:
                    message_type, payload = self.audit_queue.get_nowait()
                except queue.Empty:
                    break
                self.refreshing = False
                self.btn_refresh.config(state="normal")
                if message_type == "ok":
                    try:
                        self.apply_snapshot(payload)
                    except Exception as exc:
                        self.status_badge.config(text="● 표시 오류", bg="#4c1d24", fg=ACCENT_RED)
                        self.append_log(f"[ui] {type(exc).__name__}: {exc}")
                else:
                    self.status_badge.config(text="● 점검 오류", bg="#4c1d24", fg=ACCENT_RED)
                    self.append_log(f"[audit] {payload}")
            while True:
                try:
                    self.append_log(self.log_queue.get_nowait())
                except queue.Empty:
                    break
        finally:
            self.root.after(100, self.poll_queues)

    def apply_snapshot(self, result: dict[str, Any]) -> None:
        self.snapshot = result
        summary = result["summary"]
        input_audit = result["input_audit"]
        run_state = self.read_run_state()
        eta = pipeline_core.calculate_eta(result, run_state)
        usage = result["usage"]
        self.metrics["progress"].set(f"{summary['completion_percent']:.1f}%")
        self.metrics["files"].set(f"{summary['files_translated']} / {summary['files_total']}")
        self.metrics["rows"].set(f"{summary['rows_completed']:,} / {summary['rows_total']:,}")
        input_problem_count = summary["source_issue_count"]
        self.metrics["source"].set("정상" if input_problem_count == 0 else f"확인 {input_problem_count}")
        self.metrics["quality"].set(f"{summary['output_issue_count']}건")
        if usage["unknown_cost_requests"]:
            cost_text = f"${usage['known_cost']:.6f} + {usage['unknown_cost_requests']}건 단가 미설정"
        elif usage["requests"]:
            cost_text = f"${usage['known_cost']:.6f}"
        else:
            cost_text = "기록 없음"
        self.metrics["cost"].set(cost_text)
        self.metrics["tokens"].set(f"{usage['total_tokens']:,}")
        self.metrics["eta"].set(format_duration(eta))
        self.progress_bar["value"] = summary["completion_percent"]

        profile = result.get("profile", {})
        model = profile.get("model") or "미설정"
        endpoint = profile.get("endpoint") or "미설정"
        self.profile_summary.config(text=f"모델: {model}   |   엔드포인트: {endpoint}")
        self.profile_vars["model"].set(model)
        self.profile_vars["endpoint"].set(endpoint)
        self.profile_vars["workers"].set(str(profile.get("workers") or "—"))
        self.profile_vars["batch"].set(str(profile.get("batch_size") or "—"))
        self.profile_vars["context"].set(str(profile.get("context_size") or "—"))
        self.profile_vars["retries"].set(str(profile.get("max_retries") or "—"))
        self.profile_vars["error_wait"].set(str(profile.get("error_wait") or "—"))
        auto_adjust = profile.get("auto_adjust_workers")
        self.profile_vars["worker_adjust"].set(
            "켬" if auto_adjust is True else "끔" if auto_adjust is False else "—"
        )
        self.profile_vars["backend"].set(str(result.get("backend", {}).get("path") or "없음"))
        if not self.price_model.get():
            self.price_model.set("deepseek-flash")

        if run_state.get("status") == "running" and self.runner and self.runner.is_running():
            self.set_running_ui(True)
        else:
            self.set_running_ui(False)
        self.populate_files()
        self.populate_issues()
        self.populate_input_audit()
        self.populate_categories()
        self.populate_usage()
        self.update_proxy_status()

        if self.runner and self.runner.is_running() and not self._auto_refresh_scheduled:
            self._auto_refresh_scheduled = True
            self.root.after(2500, self.schedule_running_refresh)
        self.append_log(
            "[audit] "
            + pipeline_core.format_summary(result)
        )

    def schedule_running_refresh(self) -> None:
        self._auto_refresh_scheduled = False
        if self.runner and self.runner.is_running():
            self.request_refresh()

    def set_running_ui(self, running: bool) -> None:
        if running:
            self.btn_start.config(state="disabled")
            self.btn_stop.config(state="normal")
            self.status_badge.config(text="● GalTransl 실행 중", bg="#1b4d3e", fg=ACCENT_GREEN)
        else:
            self.btn_start.config(state="normal")
            self.btn_stop.config(state="disabled")
            if not self.refreshing:
                self.status_badge.config(text="● 대기 중", bg="#2a3f35", fg=ACCENT_GREEN)

    def populate_files(self) -> None:
        self.file_tree.delete(*self.file_tree.get_children())
        for item in self.snapshot.get("files", []):
            status_labels = {
                "translated": "완료",
                "qa_warning": "QA 확인",
                "blocked": "오류",
                "source_warning": "원문 확인",
                "pending": "대기",
            }
            self.file_tree.insert(
                "",
                "end",
                values=(
                    status_labels.get(item["status"], item["status"]),
                    item["file"],
                    item["row_count"],
                    item["completed_rows"],
                    f"{item['source_chars']:,}",
                    item["issue_count"],
                ),
                tags=(item["status"],),
            )

    def populate_issues(self) -> None:
        self.issue_tree.delete(*self.issue_tree.get_children())
        self.visible_issues = {}
        self.selected_issue = None
        self.qa_action_label.config(text="")
        self.qa_detail_label.config(text="검수할 QA 항목을 선택하세요.")
        for widget in (self.qa_source_text, self.qa_english_text, self.qa_translation_edit):
            widget.config(state="normal")
            widget.delete("1.0", "end")
        self.qa_source_text.config(state="disabled")
        self.qa_english_text.config(state="disabled")
        selected = self.issue_filter.get()
        issues = self.snapshot.get("issues", [])
        if selected != "전체":
            issues = [item for item in issues if item.get("scope") == selected]
        for index, item in enumerate(issues[:2000]):
            item_id = f"issue_{index}"
            self.visible_issues[item_id] = item
            explanation = pipeline_core.explain_issue(item)
            self.issue_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    item["scope"],
                    item["type"],
                    item["file"],
                    item["ffbe_id"],
                    explanation["summary"],
                ),
            )
        self.quality_summary.config(
            text=f"{len(issues):,}건" if len(issues) <= 2000 else f"{len(issues):,}건 중 2,000건 표시"
            + f" · 승인 {self.snapshot.get('summary', {}).get('accepted_issue_count', 0):,}건"
        )

    def on_issue_selected(self, _event: Any = None) -> None:
        selected = self.issue_tree.selection()
        if not selected:
            return
        issue = self.visible_issues.get(selected[0])
        if not issue:
            return
        self.selected_issue = issue
        try:
            context = pipeline_core.get_issue_context(
                issue["file"],
                issue["ffbe_id"],
                PROJECT_DIR,
            )
        except Exception as exc:
            self.qa_detail_label.config(text=f"상세 로드 실패: {exc}")
            return
        self.qa_context = context
        speaker = context.get("name") or "화자 없음"
        self.qa_detail_label.config(
            text=(
                f"{issue['file']} / {issue['ffbe_id']} / {issue['type']} / {speaker}"
            )
        )
        explanation = pipeline_core.explain_issue(issue, context)
        self.qa_reason_label.config(
            text=f"문제: {explanation['reason']}\n조치: {explanation['action']}"
        )
        self.qa_source_text.config(state="normal")
        self.qa_source_text.delete("1.0", "end")
        self.qa_source_text.insert("1.0", context.get("source", ""))
        self.qa_source_text.config(state="disabled")
        self.qa_english_text.config(state="normal")
        self.qa_english_text.delete("1.0", "end")
        self.qa_english_text.insert("1.0", context.get("english", ""))
        self.qa_english_text.config(state="disabled")
        self.qa_translation_edit.config(state="normal")
        self.qa_translation_edit.delete("1.0", "end")
        self.qa_translation_edit.insert("1.0", context.get("translation", ""))
        self.qa_action_label.config(text="번역을 고친 뒤 저장하거나, 의도된 문장이면 승인하세요.")

    def save_issue_translation(self) -> None:
        if not self.selected_issue:
            messagebox.showwarning("QA 검수", "먼저 QA 항목을 선택하세요.")
            return
        context = self.qa_context
        text = self.qa_translation_edit.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showerror("QA 검수", "번역문이 비어 있습니다.")
            return
        try:
            pipeline_core.update_translation_message(
                str(context["file"]),
                str(context["ffbe_id"]),
                text,
                PROJECT_DIR,
            )
        except Exception as exc:
            messagebox.showerror("QA 저장 실패", str(exc))
            return
        self.append_log(
            f"[qa] saved {context['file']} / {context['ffbe_id']}"
        )
        self.request_refresh()

    def accept_selected_issue(self) -> None:
        if not self.selected_issue:
            messagebox.showwarning("QA 검수", "먼저 QA 항목을 선택하세요.")
            return
        pipeline_core.accept_qa_issue(self.selected_issue, project_dir=PROJECT_DIR)
        self.append_log(
            f"[qa] accepted {self.selected_issue['file']} / "
            f"{self.selected_issue['ffbe_id']} / {self.selected_issue['type']}"
        )
        self.request_refresh()

    def populate_input_audit(self) -> None:
        audit = self.snapshot.get("input_audit", {})
        meta = self.snapshot.get("meta", {})
        issues = [
            item
            for item in self.snapshot.get("issues", [])
            if item.get("scope") in {"source", "meta"}
        ]
        self.input_summary.config(state="normal")
        self.input_summary.delete("1.0", "end")
        self.input_summary.insert(
            "end",
            "원문 정리 결과는 실제 gt_input JSON 전수 검사 기준입니다.\n\n"
            f"파일: {audit.get('files', 0):,}개   행: {audit.get('rows', 0):,}개   "
            f"일본어 포함: {audit.get('japanese_rows', 0):,}개\n"
            f"비일본어 라틴 원문: {audit.get('non_japanese_latin', 0):,}개   "
            f"숫자·기호만: {audit.get('neutral_text', 0):,}개   "
            f"이름 없음: {audit.get('missing_names', 0):,}개\n"
            f"파싱 오류: {audit.get('parse_errors', 0):,}   "
            f"ID 중복: {audit.get('duplicate_ids', 0):,}   "
            f"빈 문장: {audit.get('blank_messages', 0):,}\n"
            f"고유 문장: {audit.get('unique_messages', 0):,}   "
            f"중복 재사용 가능 행: {audit.get('duplicate_message_rows', 0):,}\n\n"
            "스크립트 메타데이터 연결\n"
            f"기준 행: {meta.get('rows', 0):,}   고유 키: {meta.get('unique_keys', 0):,}   "
            f"입력 누락: {meta.get('missing_source_entries', 0):,}   "
            f"미참조 기준: {meta.get('unreferenced_input_entries', 0):,}   "
            f"일본어 불일치: {meta.get('japanese_mismatches', 0):,}",
        )
        self.input_summary.config(state="disabled")
        self.input_issue_tree.delete(*self.input_issue_tree.get_children())
        for item in issues[:2000]:
            self.input_issue_tree.insert(
                "",
                "end",
                values=(item["type"], item["file"], item["ffbe_id"], item["detail"]),
            )

    def populate_categories(self) -> None:
        records = self.snapshot.get("categories", [])
        self.csv_records = {item["name"]: item for item in records}
        names = list(self.csv_records)
        current = self.csv_selector.get()
        self.csv_selector.configure(values=names)
        if names and current not in self.csv_records:
            self.csv_selector.set(names[0])
            self.load_selected_csv()
        elif not names:
            self.csv_selector.set("")
            self.csv_count.config(text="CSV 없음")

    def load_selected_csv(self, _event: Any = None) -> None:
        name = self.csv_selector.get()
        record = self.csv_records.get(name)
        if not record:
            return
        path = Path(record["path"])
        rows: list[list[str]] = []
        try:
            with path.open("r", encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.reader(stream))
        except (OSError, csv.Error) as exc:
            self.csv_count.config(text=f"읽기 오류: {exc}")
            return
        if not rows:
            return
        self.current_csv_headers = rows[0]
        self.current_csv_rows = rows[1:]
        self.csv_tree.delete(*self.csv_tree.get_children())
        columns = [f"c{index}" for index in range(len(self.current_csv_headers))]
        self.csv_tree.configure(columns=columns)
        for index, heading in enumerate(self.current_csv_headers):
            self.csv_tree.heading(columns[index], text=heading)
            self.csv_tree.column(columns[index], width=160, minwidth=80, stretch=True)
        for row in self.current_csv_rows[:1000]:
            padded = row + [""] * (len(columns) - len(row))
            self.csv_tree.insert("", "end", values=padded[: len(columns)])
        self.csv_count.config(
            text=f"{len(self.current_csv_rows):,}행"
            + (" 중 1,000행 표시" if len(self.current_csv_rows) > 1000 else "")
        )

    def show_selected_csv_row(self, _event: Any = None) -> None:
        selected = self.csv_tree.selection()
        if not selected:
            return
        values = self.csv_tree.item(selected[0], "values")
        self.csv_detail.delete("1.0", "end")
        for header, value in zip(self.current_csv_headers, values):
            self.csv_detail.insert("end", f"{header}: {value}\n")

    def populate_usage(self) -> None:
        usage = self.snapshot.get("usage", {})
        run_state = self.read_run_state()
        expected_total = None
        completed = int(self.snapshot.get("summary", {}).get("rows_completed", 0))
        total = int(self.snapshot.get("summary", {}).get("rows_total", 0))
        if usage.get("known_cost") and completed:
            expected_total = usage["known_cost"] / completed * total
        lines = [
            f"원장 파일: {usage.get('ledger_path', '')}",
            f"요청: {usage.get('requests', 0):,}   성공: {usage.get('successful_requests', 0):,}   실패: {usage.get('failed_requests', 0):,}",
            f"입력 토큰: {usage.get('prompt_tokens', 0):,}   출력 토큰: {usage.get('completion_tokens', 0):,}   캐시 토큰: {usage.get('cached_tokens', 0):,}",
            f"계량된 비용: ${usage.get('known_cost', 0):.8f}   단가 미설정 요청: {usage.get('unknown_cost_requests', 0):,}",
            f"피크 비용: ${usage.get('peak_cost', 0):.8f} ({usage.get('peak_requests', 0):,}회)   "
            f"오프피크 비용: ${usage.get('off_peak_cost', 0):.8f} ({usage.get('off_peak_requests', 0):,}회)",
            f"비용 기반 전체 예상액: {f'${expected_total:.8f}' if expected_total is not None else '산출 불가'}",
            "",
            f"실행 상태: {run_state.get('status', '없음')}",
            f"실행 모델: {run_state.get('model', '—')}",
            f"시작 시 완료 행: {run_state.get('baseline_rows_completed', '—')}",
            "",
            "정확한 비용은 usage_monitor.py 프록시를 거친 요청만 계산합니다.",
            "프록시: python usage_monitor.py --port 41990 --upstream https://api.deepseek.com",
            "GalTransl endpoint를 http://127.0.0.1:41990/v1 로 두고 실행하세요.",
        ]
        for model, values in usage.get("models", {}).items():
            lines.append(
                f"모델 {model}: {values.get('requests', 0)}회, "
                f"{values.get('total_tokens', 0):,} tokens, ${values.get('cost', 0):.8f}, "
                f"단가 미설정 {values.get('unknown_cost_requests', 0)}회"
            )
        self.usage_summary.config(state="normal")
        self.usage_summary.delete("1.0", "end")
        self.usage_summary.insert("1.0", "\n".join(lines))
        self.usage_summary.config(state="disabled")

    def read_monitoring_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.monitoring_state_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def write_monitoring_state(self, state: dict[str, Any]) -> None:
        temp_path = self.monitoring_state_path.with_suffix(".json.tmp")
        temp_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.monitoring_state_path)

    def update_proxy_status(self) -> None:
        if self.proxy is not None and self.proxy.is_running():
            self.proxy_status.config(
                text=f"실행 중 · {self.proxy.endpoint}",
                fg=ACCENT_GREEN,
            )
            return
        state = self.read_monitoring_state()
        if state.get("active"):
            self.proxy_status.config(text="이전 설정 남음 · 복구 가능", fg=ACCENT_YELLOW)
        else:
            self.proxy_status.config(text="중지됨", fg=TEXT_MUTED)

    def enable_monitoring_mode(self) -> None:
        profile = pipeline_core.read_galtransl_profile()
        current_endpoint = str(profile.get("endpoint") or "").rstrip("/")
        if not current_endpoint:
            messagebox.showerror("모니터링 모드", "GalTransl endpoint를 먼저 설정하세요.")
            return
        existing = self.read_monitoring_state()
        proxy_port = int(os.environ.get("FFBE_PROXY_PORT", "41990"))
        proxy_endpoint = f"http://127.0.0.1:{proxy_port}/v1"
        if current_endpoint == proxy_endpoint and existing.get("original_endpoint"):
            original_endpoint = str(existing["original_endpoint"])
            upstream = str(existing.get("upstream") or "")
        else:
            original_endpoint = current_endpoint
            upstream = current_endpoint[:-3] if current_endpoint.endswith("/v1") else current_endpoint
        if not upstream:
            messagebox.showerror("모니터링 모드", "원본 API endpoint를 해석하지 못했습니다.")
            return

        self.proxy = usage_monitor.UsageProxyProcess(
            port=proxy_port,
            upstream=upstream,
            ledger_path=self.runtime_dir / "usage_ledger.jsonl",
            pricing_path=self.runtime_dir / "pricing.json",
            router_client="ffbe-galtransl" if upstream.rstrip("/") == "http://macmini.local:4010" else "",
        )
        try:
            self.proxy.start()
            pipeline_core.replace_config_endpoint(pipeline_core.CONFIG_PATH, self.proxy.endpoint)
        except Exception as exc:
            if self.proxy is not None:
                self.proxy.stop()
            messagebox.showerror("모니터링 모드", str(exc))
            return
        self.write_monitoring_state(
            {
                "active": True,
                "original_endpoint": original_endpoint,
                "upstream": upstream,
                "proxy_endpoint": self.proxy.endpoint,
                "enabled_at": pipeline_core.utc_now(),
            }
        )
        self.append_log(f"[proxy] monitoring enabled: {upstream} -> {self.proxy.endpoint}")
        self.update_proxy_status()
        self.request_refresh()

    def disable_monitoring_mode(self) -> None:
        state = self.read_monitoring_state()
        original_endpoint = str(state.get("original_endpoint") or "")
        proxy_endpoint = str(state.get("proxy_endpoint") or "http://127.0.0.1:41990/v1")
        current = str(pipeline_core.read_galtransl_profile().get("endpoint") or "").rstrip("/")
        try:
            if original_endpoint and current == proxy_endpoint:
                pipeline_core.replace_config_endpoint(pipeline_core.CONFIG_PATH, original_endpoint)
            if self.proxy is not None:
                self.proxy.stop()
            if state:
                state["active"] = False
                state["restored_at"] = pipeline_core.utc_now()
                self.write_monitoring_state(state)
        except Exception as exc:
            messagebox.showerror("모니터링 복구", str(exc))
            return
        self.proxy = None
        self.append_log("[proxy] monitoring disabled and endpoint restored")
        self.update_proxy_status()
        self.request_refresh()

    def start_translation(self) -> None:
        if not self.snapshot:
            messagebox.showwarning("실행", "프로젝트 상태를 먼저 확인하세요.")
            return
        backend_raw = self.snapshot.get("backend", {}).get("path", "")
        if not backend_raw:
            messagebox.showerror("실행", "GalTransl 백엔드를 찾지 못했습니다.")
            return
        summary = self.snapshot["summary"]
        profile = pipeline_core.read_galtransl_profile()
        endpoint = str(profile.get("endpoint") or "")
        if endpoint.rstrip("/") == "http://macmini.local:4010/v1":
            messagebox.showwarning("KeyRouter 연결", "KeyRouter 사용 전 '모니터링 모드 시작'을 눌러 주세요.")
            return
        if self.read_monitoring_state().get("active") and (self.proxy is None or not self.proxy.is_running()):
            messagebox.showwarning("모니터링 연결", "모니터링 프록시가 실행 중이 아닙니다. 모니터링 모드를 다시 시작하세요.")
            return
        monitoring_note = (
            "계량 프록시 경유: 이번 실행의 토큰과 비용을 기록합니다."
            if endpoint.startswith("http://127.0.0.1:")
            else "직접 API 연결: 이번 실행 비용은 usage ledger에 자동 기록되지 않습니다."
        )
        confirmed = messagebox.askyesno(
            "GalTransl 실행",
            "GalTransl를 실행하면 설정된 API 사용료가 발생할 수 있습니다.\n\n"
            f"모델: {profile.get('model') or '미설정'}\n"
            f"엔드포인트: {profile.get('endpoint') or '미설정'}\n"
            f"현재 입력: {summary['rows_total']:,}행 / {summary['files_total']:,}파일\n\n"
            f"{monitoring_note}\n\n"
            "계속하시겠습니까?",
        )
        if not confirmed:
            return
        self.runner = pipeline_core.TranslationRunner(
            PROJECT_DIR,
            Path(backend_raw),
            self.runtime_dir,
            on_line=lambda line: self.log_queue.put(line),
        )
        try:
            state = self.runner.start()
        except Exception as exc:
            messagebox.showerror("실행 실패", str(exc))
            return
        self.set_running_ui(True)
        self.append_log(f"[runner] started pid={state['pid']}")

    def stop_translation(self) -> None:
        if self.runner is None or not self.runner.is_running():
            return
        if not messagebox.askyesno("중지", "현재 GalTransl 프로세스를 중지하시겠습니까?"):
            return
        self.runner.stop()
        self.append_log("[runner] stop requested")
        self.set_running_ui(False)

    def read_run_state(self) -> dict[str, Any]:
        if self.runner is not None:
            return self.runner.read_state()
        return pipeline_core.TranslationRunner(
            PROJECT_DIR,
            Path(""),
            self.runtime_dir,
        ).read_state()

    def append_log(self, text: str) -> None:
        if not text:
            return
        timestamp = time.strftime("[%H:%M:%S]")
        self.log_text.insert("end", f"{timestamp} {text}\n")
        self.log_text.see("end")
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 2500:
            self.log_text.delete("1.0", "100.0")

    def open_path(self, path: Path) -> None:
        try:
            os.startfile(str(path))
        except OSError as exc:
            messagebox.showerror("폴더 열기", str(exc))

    def close(self) -> None:
        if self.runner is not None and self.runner.is_running():
            if not messagebox.askyesno("종료", "GalTransl가 실행 중입니다. 중지하고 종료하시겠습니까?"):
                return
            self.runner.stop()
        if self.proxy is not None or self.read_monitoring_state().get("active"):
            self.disable_monitoring_mode()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    FFBEPipelineDashboard(root)
    root.mainloop()


if __name__ == "__main__":
    main()
