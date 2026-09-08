"""Houdiniにドッキングするリッチな違反一覧パネル（PySide6のみ、houは一切importしない）。

Houdiniへの実際のドッキング・実`hou`呼び出しは
`scene_doctor/adapters/houdini_panel_launch.py`に閉じ込め（ADR-0007）、
本モジュールは3つのコールバックを受け取るだけの疎結合な設計にすることで、
`QT_QPA_PLATFORM=offscreen`のヘッドレスQApplication上で本物のPySide6ウィジェットとして
テストできる（`tests/test_panel.py`, pytest-qtの`qtbot`使用）。
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from scene_doctor.report import SceneReport, Severity
from scene_doctor.ui.panel_view_model import ViolationRow, build_rows, filter_rows

# ツリー列インデックス
COLUMN_SEVERITY = 0
COLUMN_CATEGORY = 1
COLUMN_TARGET_PATH = 2
COLUMN_MESSAGE = 3
COLUMN_RENAME_CANDIDATE = 4

COLUMN_HEADERS = ["Severity", "Category", "Target Path", "Message", "Rename Candidate"]

# severity列のアイコン色分け（error=赤 / warning=黄）
SEVERITY_COLORS = {
    Severity.ERROR: QColor("#e53935"),
    Severity.WARNING: QColor("#fdd835"),
}

# node_pathを行に紐付けるためのカスタムデータロール
NODE_PATH_ROLE = int(Qt.ItemDataRole.UserRole)


class SceneDoctorPanel(QDockWidget):
    """Scene Doctorの違反一覧を表示・操作するドッキングパネル。

    Houdini本体（hou）には一切依存せず、以下3つのコールバックを注入されることで
    実際の検証実行・ノード選択・エクスポート処理から疎結合になっている。

    Args:
        run_checks_callback: 「Run Checks」ボタン押下時に呼ばれ、新しい`SceneReport`を返す。
        select_node_callback: 違反行がクリックされた時、対象ノードパスを引数に呼ばれる。
        export_callback: エクスポートボタン押下時、(形式, 出力先パス)を引数に呼ばれる。
    """

    FILTER_ALL = "All"

    def __init__(
        self,
        run_checks_callback: Callable[[], SceneReport],
        select_node_callback: Callable[[str], None],
        export_callback: Callable[[str, str], None],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Scene Doctor", parent)

        self._run_checks_callback = run_checks_callback
        self._select_node_callback = select_node_callback
        self._export_callback = export_callback
        self._rows: list[ViolationRow] = []

        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        container = QWidget(self)
        layout = QVBoxLayout(container)

        toolbar = QHBoxLayout()
        self.run_checks_button = QPushButton("Run Checks", container)
        self.export_path_edit = QLineEdit(container)
        self.export_path_edit.setPlaceholderText("Export destination path (optional)")
        self.export_csv_button = QPushButton("Export CSV", container)
        self.export_json_button = QPushButton("Export JSON", container)
        toolbar.addWidget(self.run_checks_button)
        toolbar.addWidget(self.export_path_edit)
        toolbar.addWidget(self.export_csv_button)
        toolbar.addWidget(self.export_json_button)
        layout.addLayout(toolbar)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("Severity:", container))
        self.severity_filter = QComboBox(container)
        self.severity_filter.addItem(self.FILTER_ALL)
        for severity in Severity:
            self.severity_filter.addItem(severity.value)
        filter_bar.addWidget(self.severity_filter)

        filter_bar.addWidget(QLabel("Category:", container))
        self.category_filter = QComboBox(container)
        self.category_filter.addItem(self.FILTER_ALL)
        filter_bar.addWidget(self.category_filter)
        layout.addLayout(filter_bar)

        self.tree = QTreeWidget(container)
        self.tree.setColumnCount(len(COLUMN_HEADERS))
        self.tree.setHeaderLabels(COLUMN_HEADERS)
        layout.addWidget(self.tree)

        self.status_label = QLabel("0 violation(s)", container)
        layout.addWidget(self.status_label)

        container.setLayout(layout)
        self.setWidget(container)

    def _connect_signals(self) -> None:
        self.run_checks_button.clicked.connect(self._on_run_checks_clicked)
        self.export_csv_button.clicked.connect(self._on_export_csv_clicked)
        self.export_json_button.clicked.connect(self._on_export_json_clicked)
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        self.severity_filter.currentTextChanged.connect(self._on_filter_changed)
        self.category_filter.currentTextChanged.connect(self._on_filter_changed)

    def _on_run_checks_clicked(self) -> None:
        report = self._run_checks_callback()
        self._rows = build_rows(report)
        self._refresh_category_filter_choices()
        self._rebuild_tree()

    def _refresh_category_filter_choices(self) -> None:
        current = self.category_filter.currentText()
        categories = sorted({row.category for row in self._rows})
        self.category_filter.blockSignals(True)
        self.category_filter.clear()
        self.category_filter.addItem(self.FILTER_ALL)
        self.category_filter.addItems(categories)
        restore_index = self.category_filter.findText(current)
        self.category_filter.setCurrentIndex(restore_index if restore_index >= 0 else 0)
        self.category_filter.blockSignals(False)

    def _current_filter_values(self) -> tuple[Severity | None, str | None]:
        severity_text = self.severity_filter.currentText()
        category_text = self.category_filter.currentText()
        severity = None if severity_text == self.FILTER_ALL else Severity(severity_text)
        category = None if category_text == self.FILTER_ALL else category_text
        return severity, category

    def _rebuild_tree(self) -> None:
        self.tree.clear()
        severity, category = self._current_filter_values()
        visible_rows = filter_rows(self._rows, severity=severity, category=category)

        for row in visible_rows:
            item = QTreeWidgetItem(
                [
                    row.severity.value,
                    row.category,
                    row.target_path,
                    row.message,
                    row.rename_candidate or "",
                ]
            )
            color = SEVERITY_COLORS.get(row.severity)
            if color is not None:
                item.setForeground(COLUMN_SEVERITY, color)
            item.setData(0, NODE_PATH_ROLE, row.node_path)
            self.tree.addTopLevelItem(item)

        self.status_label.setText(f"{len(visible_rows)} violation(s)")

    def _on_filter_changed(self, _text: str) -> None:
        self._rebuild_tree()

    def _on_current_item_changed(
        self, current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        if current is None:
            return
        node_path = current.data(0, NODE_PATH_ROLE)
        if node_path:
            self._select_node_callback(str(node_path))

    def _on_export_csv_clicked(self) -> None:
        self._export("csv")

    def _on_export_json_clicked(self) -> None:
        self._export("json")

    def _export(self, fmt: str) -> None:
        # 出力先パスは`export_path_edit`に入力された値をそのまま渡す（空文字でもよい）。
        # panel.py はモーダルなファイル選択ダイアログを持たない設計にすることで、
        # QT_QPA_PLATFORM=offscreen下でもテストがブロックされず、実機（Houdini）側の
        # export_callback実装（例: hou.ui.selectFileで別途パスを尋ねる等）を自由に選べる
        # ようにしている（疎結合設計）。
        self._export_callback(fmt, self.export_path_edit.text())
