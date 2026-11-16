"""Safe per-case evidence and explicit machine-readable blocked results."""
import json
import os
import re
import sys
import traceback
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
        qa_id = dict(item.user_properties).get('qa_case_id')
        if qa_id:
            result['qa_case_id'] = qa_id
        if report.skipped and isinstance(report.longrepr, tuple):
            reason = str(report.longrepr[-1])
            if 'Blocked:' in reason:
                result['reason'] = reason.split('Blocked:', 1)[-1].strip()
        if report.failed and call.excinfo:
            result['error_type'] = type(call.excinfo.value).__name__
            local_names = {'android_ui.py', 'android_workflow_support.py', 'test_android_regression.py', 'test_android_workflows.py', 'test_create_listing.py'}
            result['failure_sites'] = [{'file': Path(str(entry.path)).name, 'function': entry.frame.code.name, 'line': entry.lineno + 1}
                for entry in call.excinfo.traceback if Path(str(entry.path)).name in local_names][-6:]
            causes = []
            cause = call.excinfo.value.__context__
            while cause and len(causes) < 3:
                causes.append({'error_type': type(cause).__name__, 'sites': [
                    {'file': Path(e.filename).name, 'function': e.name, 'line': e.lineno}
                    for e in traceback.extract_tb(cause.__traceback__)
                    if Path(e.filename).name in local_names][-6:]})
                cause = cause.__context__
            if causes:
                result['causes'] = causes
            reporter = item.config.pluginmanager.get_plugin('terminalreporter')
            if reporter:
                reporter.write_line('QA_FAILURE=' + json.dumps({'case': item.nodeid, 'error_type': result['error_type'], 'sites': result['failure_sites'], 'causes': causes}))
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
