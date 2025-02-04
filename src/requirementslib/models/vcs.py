import importlib
import os
import sys

import attr
from pip._internal.utils.temp_dir import global_tempdir_manager
from pip._internal.vcs.versioncontrol import VcsSupport

from ..environment import MYPY_RUNNING
from .url import URI

if MYPY_RUNNING:
    from typing import Any, Optional, Tuple


@attr.s(hash=True)
class VCSRepository(object):
    DEFAULT_RUN_ARGS = None

    url = attr.ib()  # type: str
    name = attr.ib()  # type: str
    checkout_directory = attr.ib()  # type: str
    vcs_type = attr.ib()  # type: str
    parsed_url = attr.ib()  # type: URI
    subdirectory = attr.ib(default=None)  # type: Optional[str]
    commit_sha = attr.ib(default=None)  # type: Optional[str]
    ref = attr.ib(default=None)  # type: Optional[str]
    repo_backend = attr.ib()  # type: Any
    clone_log = attr.ib(default=None)  # type: Optional[str]

    @parsed_url.default
    def get_parsed_url(self):
        # type: () -> URI
        return URI.parse(self.url)

    @repo_backend.default
    def get_repo_backend(self):
        if self.DEFAULT_RUN_ARGS is None:
            default_run_args = self.monkeypatch_pip()
        else:
            default_run_args = self.DEFAULT_RUN_ARGS

        VCS_SUPPORT = VcsSupport()
        backend = VCS_SUPPORT.get_backend(self.vcs_type)
        # repo = backend(url=self.url)
        if backend.run_command.__func__.__defaults__ != default_run_args:
            backend.run_command.__func__.__defaults__ = default_run_args
        return backend

    @property
    def is_local(self):
        # type: () -> bool
        url = self.url
        if "+" in url:
            url = url.split("+")[1]
        return url.startswith("file")

    def obtain(self, verbosity=1) -> None:
        if os.path.exists(
            self.checkout_directory
        ) and not self.repo_backend.is_repository_directory(self.checkout_directory):
            self.repo_backend.unpack(self.checkout_directory)
        elif not os.path.exists(self.checkout_directory):
            self.repo_backend.obtain(self.checkout_directory, self.parsed_url, verbosity)
        else:
            if self.ref:
                self.checkout_ref(self.ref)
        if not self.commit_sha:
            self.commit_sha = self.get_commit_hash()

    def checkout_ref(self, ref):
        # type: (str) -> None
        rev_opts = self.repo_backend.make_rev_options(ref)
        if not any(
            [
                self.repo_backend.is_commit_id_equal(self.checkout_directory, ref),
                self.repo_backend.is_commit_id_equal(self.checkout_directory, rev_opts),
                self.is_local,
            ]
        ):
            self.update(ref)

    def update(self, ref):
        # type: (str) -> None
        target_ref = self.repo_backend.make_rev_options(ref)
        self.repo_backend.update(self.checkout_directory, self.url, target_ref)
        self.commit_sha = self.get_commit_hash()

    def get_commit_hash(self, ref=None):
        # type: (Optional[str]) -> str
        with global_tempdir_manager():
            return self.repo_backend.get_revision(self.checkout_directory)

    @classmethod
    def monkeypatch_pip(cls):
        # type: () -> Tuple[Any, ...]
        target_module = VcsSupport.__module__
        pip_vcs = importlib.import_module(target_module)
        run_command_defaults = pip_vcs.VersionControl.run_command.__func__.__defaults__
        # set the default to not write stdout, the first option sets this value
        new_defaults = [False] + list(run_command_defaults)[1:]
        new_defaults = tuple(new_defaults)
        pip_vcs.VersionControl.run_command.__func__.__defaults__ = new_defaults
        sys.modules[target_module] = pip_vcs
        cls.DEFAULT_RUN_ARGS = new_defaults
        return new_defaults
