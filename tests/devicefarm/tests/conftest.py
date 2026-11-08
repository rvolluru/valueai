"""Safe per-case evidence and explicit machine-readable blocked results."""
import json
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
RESULTS = []


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if report.when == 'call' or (report.when == 'setup' and report.outcome != 'passed'):
        # Never serialize longrepr: WebDriver exceptions can contain credentials.
        result = {'case': item.nodeid, 'phase': report.when,
                  'status': {'passed': 'Pass', 'failed': 'Fail', 'skipped': 'Blocked'}[report.outcome],
                  'duration_seconds': round(report.duration, 2)}
        if report.skipped and isinstance(report.longrepr, tuple):
            reason = str(report.longrepr[-1])
            if 'Blocked:' in reason:
                result['reason'] = reason.split('Blocked:', 1)[-1].strip()
        RESULTS.append(result)
        app = item.funcargs.get('ui')
        if app and not report.skipped:
            folder = Path(os.environ.get('DEVICEFARM_LOG_DIR', 'output/devicefarm')) / 'cases'
            folder.mkdir(parents=True, exist_ok=True)
            try:
                app.capture(folder / (re.sub(r'[^A-Za-z0-9_-]', '_', item.nodeid)[-150:] + '.png'))
            except Exception:
                pass


def pytest_sessionfinish(session, exitstatus):
    folder = Path(os.environ.get('DEVICEFARM_LOG_DIR', 'output/devicefarm'))
    folder.mkdir(parents=True, exist_ok=True)
    reported = {x['case'] for x in RESULTS}
    RESULTS.extend({'case': item.nodeid, 'status': 'Not Run'} for item in session.items if item.nodeid not in reported)
    counts = {status: sum(x['status'] == status for x in RESULTS) for status in ['Pass', 'Fail', 'Blocked', 'Not Run']}
    (folder / 'android-case-results.json').write_text(json.dumps({'counts': counts, 'cases': RESULTS, 'device': os.environ.get('DEVICEFARM_DEVICE_NAME'), 'build': os.environ.get('JOUFT_TEST_BUILD_ID'), 'collection_only': bool(session.config.option.collectonly)}, indent=2))
    if os.environ.get('JOUFT_TEST_REQUIRE_COMPLETE') == '1' and (counts['Blocked'] or counts['Not Run']) and session.exitstatus == 0 and not session.config.option.collectonly:
        session.exitstatus = 2
