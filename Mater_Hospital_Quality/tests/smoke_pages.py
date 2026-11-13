"""Opens each page the way Streamlit does and reports any error.

Run from the app folder:  .venv\\Scripts\\python.exe tests\\smoke_pages.py
"""

import sys
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP))

failed = False
for page in ["views/scorecards.py", "views/control_charts.py", "views/equity.py"]:
    at = AppTest.from_file(str(APP / "app.py"), default_timeout=180)
    at.run()
    at.switch_page(page).run()
    problems = [e.value for e in at.exception] + [e.value for e in at.error]
    failed |= bool(problems)
    print(f"{page:28s} {'OK' if not problems else 'FAILED: ' + str(problems[:2])}"
          f"  (titles: {[t.value for t in at.title]}, metrics: {len(at.metric)}, "
          f"charts: {len(at.get('plotly_chart'))})")
sys.exit(1 if failed else 0)
