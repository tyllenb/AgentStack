import json
import os, sys
import time
from pathlib import Path
from packaging.version import parse as parse_version, Version
import inquirer
from agentstack import log
from agentstack.utils import term_color, get_version, get_framework, get_base_dir
from agentstack import packaging


AGENTSTACK_PACKAGE = 'agentstack'
CI_ENV_VARS = [
    'CI',
    'GITHUB_ACTIONS',
    'GITLAB_CI',
    'TRAVIS',
    'CIRCLECI',
    'JENKINS_URL',
    'TEAMCITY_VERSION',
]

LAST_CHECK_FILE_PATH = get_base_dir() / ".cli-last-update"
USER_GUID_FILE_PATH = get_base_dir() / ".cli-user-guid"
INSTALL_PATH = Path(sys.executable).parent.parent
ENDPOINT_URL = "https://pypi.org/simple"
CHECK_EVERY = 3600  # hour


def _is_ci_environment():
    """Detect if we're running in a CI environment"""
    return any(os.getenv(var) for var in CI_ENV_VARS)


def get_latest_version(package: str) -> Version:
    """Get version information from PyPi to save a full package manager invocation"""
    import requests  # defer import until we know we need it

    response = requests.get(
        f"{ENDPOINT_URL}/{package}/", headers={"Accept": "application/vnd.pypi.simple.v1+json"}
    )
    if response.status_code != 200:
        raise Exception(f"Failed to fetch package data from pypi.")
    data = response.json()
    return parse_version(data['versions'][-1])


def load_update_data():
    """Load existing update data or return empty dict if file doesn't exist"""
    if Path(LAST_CHECK_FILE_PATH).exists():
        try:
            with open(LAST_CHECK_FILE_PATH, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, PermissionError):
            return {}
    return {}


def should_update() -> bool:
    """Has it been longer than CHECK_EVERY since the last update check?"""
    # Allow disabling update checks with an environment variable
    if 'AGENTSTACK_UPDATE_DISABLE' in os.environ:
        return False

    # Always check for updates in CI
    if _is_ci_environment():
        return True

    data = load_update_data()
    last_check = data.get(str(INSTALL_PATH))

    if not last_check:
        return True

    return time.time() - float(last_check) > CHECK_EVERY


def record_update_check():
    """Save current timestamp for this installation"""
    # Don't record updates in CI
    if _is_ci_environment():
        return

    try:
        data = load_update_data()
        data[str(INSTALL_PATH)] = time.time()

        # Create directory if it doesn't exist
        LAST_CHECK_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

        with open(LAST_CHECK_FILE_PATH, 'w') as f:
            json.dump(data, f, indent=2)
    except (OSError, PermissionError):
        # Silently fail in CI or when we can't write
        pass


def check_for_updates(update_requested: bool = False):
    """
    `update_requested` indicates the user has explicitly requested an update.
    """
    if not update_requested and not should_update():
        return

    try:
        latest_version: Version = get_latest_version(AGENTSTACK_PACKAGE)
    except Exception as e:
        raise Exception(f"Failed to retrieve package index: {e}")

    installed_version: Version = parse_version(get_version(AGENTSTACK_PACKAGE))
    if latest_version > installed_version:
        log.info('')  # newline
        if inquirer.confirm(
            f"New version of {AGENTSTACK_PACKAGE} available: {latest_version}! Do you want to install?"
        ):
            packaging.upgrade(f'{AGENTSTACK_PACKAGE}[{get_framework()}]')
            log.success(f"{AGENTSTACK_PACKAGE} updated. Re-run your command to use the latest version.")
        else:
            log.info("Skipping update. Run `agentstack update` to install the latest version.")

    record_update_check()
