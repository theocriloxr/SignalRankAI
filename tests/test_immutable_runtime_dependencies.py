"""Actual metadata validation and fail-closed boot before application import."""
from importlib.metadata import distributions
import os
from pathlib import Path
import shutil
import subprocess

from scripts.verify_runtime_dependencies import dependency_findings


def install_metadata(root, name, version, requirements=()):
    directory = root / (name.replace('-', '_') + '-' + version + '.dist-info')
    directory.mkdir()
    (directory/'METADATA').write_text('Metadata-Version: 2.1\nName: '+name+'\nVersion: '+version+'\n'+
        ''.join('Requires-Dist: '+item+'\n' for item in requirements),encoding='utf-8')


def test_missing_and_wrong_versions_fail_without_printing_sensitive_requirements(tmp_path):
    install_metadata(tmp_path, 'app-fixture', '1.0', [
        'missing-fixture>=2', 'old-fixture>=2', 'private-fixture @ https://user:secret@example.invalid/a.whl'])
    install_metadata(tmp_path, 'old-fixture', '1.0')
    actual = dependency_findings(distributions(path=[str(tmp_path)]))
    assert actual == [
        {'package':'app-fixture','dependency':'missing-fixture','reason':'missing_dependency'},
        {'package':'app-fixture','dependency':'old-fixture','reason':'incompatible_dependency_version'},
        {'package':'app-fixture','dependency':'private-fixture','reason':'missing_dependency'},
    ]
    assert 'secret' not in str(actual) and 'example.invalid' not in str(actual)


def test_installed_versions_and_runtime_markers_are_validated_without_enabling_extras(tmp_path):
    install_metadata(tmp_path, 'app-fixture', '1.0', [
        'Current_Fixture>=2', 'optional-fixture; extra == "optional"',
        'absent-fixture; python_version < "2.0"'])
    install_metadata(tmp_path, 'current-fixture', '2.1')
    assert dependency_findings(distributions(path=[str(tmp_path)])) == []


def test_malformed_dependency_and_conflicting_distributions_fail_closed(tmp_path):
    install_metadata(tmp_path, 'app-fixture', '1.0', ['invalid @'])
    install_metadata(tmp_path, 'duplicate-fixture', '1.0')
    install_metadata(tmp_path, 'duplicate-fixture', '2.0')
    assert dependency_findings(distributions(path=[str(tmp_path)])) == [
        {'package':'app-fixture','reason':'invalid_dependency_metadata'},
        {'package':'duplicate-fixture','reason':'conflicting_installed_versions'},
    ]


def test_immutable_boot_rejects_installation_before_running_python(tmp_path):
    root = Path(__file__).resolve().parents[1]
    bash = 'C:/Program Files/Git/bin/bash.exe' if os.name == 'nt' else shutil.which('bash')
    assert bash and Path(bash).is_file(), 'the canonical entrypoint requires Bash'
    sentinel = tmp_path/'python-was-called'
    shim = tmp_path/'python'
    shim.write_text('#!/bin/sh\ntouch "'+sentinel.as_posix()+'"\nexit 99\n',encoding='utf-8')
    shim.chmod(0o755)
    env = {key:value for key,value in os.environ.items() if key.upper() in {
        'SYSTEMROOT','WINDIR','TEMP','TMP','USERPROFILE','COMSPEC','PATHEXT'}}
    env.update(PATH=str(tmp_path)+os.pathsep+('/usr/bin:/bin' if os.name != 'nt' else 'C:/Program Files/Git/usr/bin'),
               SIGNALRANK_IMMUTABLE_RUNTIME='1', INSTALL_AT_BOOT='true')
    result = subprocess.run([bash,str(root/'start.sh')],cwd=root,env=env,
                            capture_output=True,text=True,timeout=5)
    assert result.returncode == 64
    assert 'Immutable runtime prohibits installation at boot' in result.stderr
    assert not sentinel.exists()


def test_distribution_without_a_name_reports_invalid_metadata(tmp_path):
    directory = tmp_path/'broken-1.0.dist-info'
    directory.mkdir()
    (directory/'METADATA').write_text('Metadata-Version: 2.1\nVersion: 1.0\n',encoding='utf-8')
    assert dependency_findings(distributions(path=[str(tmp_path)])) == [
        {'package':'unknown','reason':'missing_package_name'},
    ]
