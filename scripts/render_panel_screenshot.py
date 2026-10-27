"""README 用に、パネル(本物の PySide6 ウィジェット)の画像を出す。`QT_QPA_PLATFORM=offscreen` で実行する。

違反の内容は、実機検証用のシーン(`verify_houdini.py`)で出る種類の例。Houdini の見た目ではなく、パネル自身の見た目。
"""

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scene_doctor.report import SceneReport, Severity, Violation  # noqa: E402
from scene_doctor.ui.panel import SceneDoctorPanel  # noqa: E402


def sample_report() -> SceneReport:
    report = SceneReport("scene.hip", "2026-10-28T00:00:00Z")
    report.violations.extend(
        [
            Violation("ngon", "/obj/BadGeoName/merge1", "primitive 4 has 8 points", Severity.ERROR),
            Violation(
                "missing_uv", "/obj/BadGeoName/merge1", "12 primitives have no UV", Severity.WARNING
            ),
            Violation(
                "duplicate_point", "/obj/BadGeoName/merge1", "8 duplicate points", Severity.WARNING
            ),
            Violation(
                "unconnected_node",
                "/obj/BadGeoName/orphan_null",
                "node has no outputs",
                Severity.WARNING,
            ),
            Violation(
                "naming",
                "/obj/BadGeoName",
                "name does not match the naming rule",
                Severity.WARNING,
                "bad_geo_name",
            ),
        ]
    )
    return report


def main() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    panel = SceneDoctorPanel(sample_report, lambda path: None, lambda fmt, path: None)
    panel.resize(980, 300)
    panel.show()
    panel.run_checks_button.click()
    for column in range(panel.tree.columnCount()):
        panel.tree.resizeColumnToContents(column)
    app.processEvents()
    out = ROOT / "docs" / "images" / "panel.png"
    panel.grab().save(str(out))
    print(out)


main()
